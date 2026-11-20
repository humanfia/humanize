"""One workspace's runs -- or one chat's -- shared by every frontend attached to them.

A run used to have one person outside it: whoever was at the one interface that started it.
The queue of lines typed at it, the questions it stopped on, who was away, which conversation
was `NeiKos496/2` -- all of it lived in that interface, because that interface was the only one.
A day's work watched by two people, or by a person and a bot, is two frontends on one run, and
each of those things has to be answered once rather than once per frontend or the two
disagree about what the run is doing.

So they are answered here, where the run is. A frontend is anything that attaches: an
interface, or a program written against the SDK. It is handed everything as
messages -- what the run's agents said, what was asked and answered, who holds which role --
and asks for everything as requests, one reply apiece. Nothing here knows whether a frontend
is in this process or on the other end of a socket: the daemon carries the same messages both
ways and hands a frontend the same :class:`hmz.daemon.link.Link` either way.

A workspace's flows are one host's, run one at a time; each chat is a host of its own beside it
(its slot, `chat:<hex>`), so that a conversation never waits on a flow nor a flow on one. A chat
is no flow (Section 8 of core.md): its host has a :class:`hmz.runtime.chatting.Chat` rather than
a run, and is the person it is had with -- what it says is asked of every frontend as what to
say next, and what is said to it (`chat` requests, which `chat.*` of daemon.md carries) answers
that. A chat's host that nobody reads, between turns, for :data:`FOLD` seconds folds the chat
away: it ends as an empty next message ends it, keeping its conversation, and saying something
in it again carries it on in the same chat.

What is held for them:

- *claims*: a role an `Outworlder` fills, held by one frontend at a time and given up when it
  goes. Only its claimant answers for it; a role nobody claims is anybody's, first answer wins.
- *away*: per role and not per frontend, since it is a fact about the run -- whether a question
  of that role is waited on -- and it outlives the frontend that said it.
- *lines*: what is said to the run's agents, queued per target and handed over one at a time.
- *keys*: which conversation is `<agent>/<n>`, numbered once so every frontend names it alike.
- *asides*: the side conversations `/btw` opens, read-only and invisible to the run.
- *history*: every record of the run, in order, so a frontend arriving late reads it all.
- *envs*: every environment the run holds, and what a frontend does in one -- its files, a
  terminal, its git (:mod:`hmz.runtime.doing.desk`).

Nothing is ever said to a frontend while anything here is locked. Each has an outbox and a
thread of its own that empties it, so one that has stopped reading costs its own memory -- up
to a ceiling, past which it is let go -- and never holds up the run or another frontend.
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
import functools
import itertools
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
import weakref
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.coganchor.agents import (
        AgentBase,
        Board,
        Event,
        Question,
        SessionBase,
    )
    from hmz.coganchor.agents.native import NativeCommand
    from hmz.runtime.chatting import Prefer, Role
    from hmz.runtime.doing.core import Hmz, Holding
    from hmz.runtime.doing.running import Chatting, Run
    from hmz.runtime.flowing.spi import Placement
    from hmz.runtime.kept import Runs

__all__ = ["FOLD", "Host", "assistant", "chat_checked", "record"]

#: How long one text in a message may be before the rest of it is counted instead. A turn's
#: answer is kilobytes; a tool that printed a file is the case this is for, and a frame of the
#: socket carrying it has a ceiling of its own.
_LONGEST = 256 * 1024

#: What a message that shows something carries whole, never cut: the schema a question is
#: answered in, and the context beside it, which the runtime holds to 16 MiB itself.
_WHOLE = frozenset({"schema", "context"})

#: The messages that carry such context.
_SHOWING = frozenset({"asked", "shown", "pending"})

#: How much of a run is kept for a frontend that arrives late, in bytes as the messages are
#: written. The oldest whole records go first, and are counted.
_KEPT = 32 << 20

#: How far behind a frontend may fall before it is let go of: a whole replay fits under it.
_BEHIND = 64 << 20

#: How often the state nothing announces -- what is open, what is running, what it spent --
#: is looked at, and how often a question being waited on looks at whether it still is.
_TICK = 0.5

#: How often what a run has spent is said, at most.
_SPENDING = 1.0

#: How many of a run's conversations are kept to open an aside on, newest kept.
_SIDES = 256

#: What a question an `Outworlder` asks is filed under, ahead of the role, as a view key.
_OUTWORLDER = "outworlder:"

#: What a flow told to stop and not yet gone is doing, in the interface's own words.
_UNWINDING = "it is closing out the turn it was in"

#: How long a chat's host waits, between turns and with nobody attached, before the chat
#: folds away: long enough to step away to another view and come back to it still going.
FOLD = 60.0

#: The role a chat's questions are filed under: the person it is had with, who is nobody's
#: outworlder but is asked as one is.
_PERSON = "human"

#: What a native line said in a chat is queued for: the next turn alone, which it is, and never
#: the turn open as it is said, which would take it as words.
_NATIVE = "native:"

#: How long a chat started waits to be told its name before the start is answered without it.
_NAMING = 30.0

#: Why a chat that has folded away takes nothing more (Section 4.13.8 of daemon.md).
_FOLDED = "this chat has folded away; carry it on with chat.start"

#: Why a chat that has ended takes nothing more.
_ENDED = "this chat has ended; carry it on with chat.start"

#: Why a chat with no turn open is not stopped (Section 4.25.6.2 of daemon.md).
_NO_TURN = "no turn is open, so there is nothing to stop"

#: Why a chat's host takes no line nor answer of `epic.say` (Section 4.10.1.3 of daemon.md).
_TO_CHAT = "say it to the chat with chat.say"

#: How long closing waits for the runs it stopped to let go of what they made -- a container
#: taken down, a session closed -- before whoever closed the host goes on without them.
_LETTING_GO = 15.0


def record(
    agent: AgentBase,
    session: SessionBase | None,
    event: Event,
    *,
    key: str = "",
    run: int = 0,
) -> dict[str, Any]:
    """One thing an agent said, as every frontend reads it and `hmz exec --json` writes it.

    Args:
      agent: Whose turn said it.
      session: The conversation it was said in, or None for something the agent said for all
        of them.
      event: What was said.
      key: The transcript it goes on: the conversation's `<agent>/<n>`, or where the agent's
        words go when no one conversation said them.
      run: Which run of the host it belongs to, or 0 for none.

    Returns:
      The record, JSON-native: `session` is `key` where the event named a conversation and
      "" where it did not, and `ident` is what the backend calls that conversation, "" until
      it has said.
    """
    return {
        "type": "event",
        "run": run,
        "key": key,
        "session": key if session is not None else "",
        "agent": agent.id,
        "cli": agent.backend,
        "model": agent.config.model,
        # `named` rather than `id`: a session is named by the backend as its first turn
        # starts, and asking for the id before that raises.
        "ident": (session.named or "") if session is not None else "",
        "kind": event.kind,
        "text": event.text,
        "whose": event.whose,
        "tokens": dict(event.tokens),
        "spent": dict(event.spent),
        "at": time.time(),
        "mono": time.monotonic(),
    }


def _clipped(said: Any, longest: int = _LONGEST, *, shows: bool = False) -> Any:
    """What a message says, with any text too long to carry cut and the rest counted.

    In a message that `shows` -- `asked`, `shown` and `pending` -- the `schema` and the
    `context` beside the question are carried whole.
    """
    if isinstance(said, str):
        if len(said) <= longest:
            return said
        return f"{said[:longest]}… ({len(said) - longest} more characters)"
    if isinstance(said, dict):
        return {
            key: value
            if shows and key in _WHOLE
            else _clipped(value, longest, shows=shows)
            for key, value in said.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(said, list):
        return [_clipped(one, longest, shows=shows) for one in said]  # pyright: ignore[reportUnknownVariableType]
    return said


def _secret(node: Mapping[str, Any]) -> bool:
    """Whether a field of a schema holds a secret (`hmz:widget` `secret`, or a password)."""
    extra: Any = node.get("json_schema_extra")
    widget: Any = node.get("hmz:widget")
    if widget is None and isinstance(extra, Mapping):
        widget = cast("Mapping[str, Any]", extra).get("hmz:widget")
    return widget == "secret" or node.get("format") == "password"


def _unsecret(text: str, schema: Mapping[str, Any] | None) -> str:
    """An answer as it is recorded: the JSON of a value with each secret field written `***`.

    The flow is given the answer whole; what every frontend and the epic's history keep of it
    never holds a secret.
    """
    if schema is None:
        return text
    try:
        value = json.loads(text)
    except ValueError:
        return text
    defs = cast("Mapping[str, Any]", schema.get("$defs") or {})

    def node_of(node: Any) -> Mapping[str, Any]:
        if not isinstance(node, Mapping):
            return {}
        held = cast("Mapping[str, Any]", node)
        ref = held.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return node_of(defs.get(ref.removeprefix("#/$defs/")))
        branches: Any = held.get("anyOf") or ()
        for branch in cast("Sequence[Any]", branches):
            if isinstance(branch, Mapping):
                one = cast("Mapping[str, Any]", branch)
                if one.get("type") != "null":
                    return {**held, **node_of(one)}
        return held

    def hidden(said: Any, node: Mapping[str, Any]) -> Any:
        if not isinstance(said, dict):
            return said
        properties = cast("Mapping[str, Any]", node.get("properties") or {})
        kept = dict(cast("dict[str, Any]", said))
        for name, raw in properties.items():
            if name not in kept:
                continue
            field = node_of(raw)
            if _secret(cast("Mapping[str, Any]", raw)) or _secret(field):
                kept[name] = "***"
            else:
                kept[name] = hidden(kept[name], field)
        return kept

    return json.dumps(hidden(value, node_of(schema)), ensure_ascii=False)


def _sized(message: dict[str, Any]) -> int:
    """How many bytes a message comes to written, which is what every ceiling is kept in."""
    return len(json.dumps(message, default=str, ensure_ascii=False).encode())


def _ok(**said: Any) -> dict[str, Any]:
    return {"ok": True, **said}


def _no(
    why: str, code: int | None = None, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A refusal, saying why, and the status code and data the daemon refuses it with.

    Without a code, the daemon refuses a call to an epic with 409.
    """
    return {
        "ok": False,
        "why": why,
        **({"code": code} if code is not None else {}),
        **({"data": data} if data is not None else {}),
    }


def _user() -> str:
    """Who is at this end, which a frontend is named for until it says otherwise."""
    said = os.environ.get("HUMANIZE_NAME", "")
    if said:
        return said
    import getpass

    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return "somebody"


def _json(model: Any) -> Any:
    """A pydantic model as JSON-native values, `Infinity` spelled as it reads back; None, None."""
    return None if model is None else json.loads(model.model_dump_json())


def _returned(value: Any) -> Any:
    """What a flow returned, as JSON: every value that is not JSON-native as its text."""
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return str(value)


def _epic_of(shown: _Run | None, kind: str = "flow") -> str:
    """The name of the epic a run is written into, or "" before it has one or for a chat.

    Args:
      shown: The run.
      kind: `flow`, or `chat` for the name of the chat a chat is written into instead.
    """
    if shown is None or shown.run.kind != kind:
        return ""
    epic = shown.run.epic
    return epic.name if epic is not None else ""


def _spoken(given: Mapping[str, Any]) -> dict[str, str]:
    """What each role was given, as the words `-a` or `-e` would spell it."""
    return {
        role: said if isinstance(said, str) else str(getattr(said, "spec", said))
        for role, said in given.items()
    }


def _placed(where: Placement | None) -> dict[str, Any] | None:
    """Where a session works, as a frontend is told it, or None where its driver did not say.

    The role it fills, which machine and where on it, and whether its agent is anchored there:
    running on this machine, with what it runs landing on that one.
    """
    if where is None:
        return None
    return {
        "role": where.env,
        "kind": str(where.backend),
        "target": where.provider,
        "workdir": str(where.workdir),
        "anchored": where.machine is not None,
    }


def _works_at(where: Placement, driver: Any) -> bool:
    """Whether a session placed `where` works in the directory a driver is at."""
    try:
        return (
            str(where.workdir) == str(driver.workdir)
            and str(where.backend) == str(driver.backend)
            and where.provider == driver.provider
        )
    except Exception:  # noqa: BLE001 -- a driver that cannot say where it is is nowhere
        return False


#: Every request about an environment, each served by :class:`hmz.runtime.doing.desk.Desk`.
_ENV_METHODS = (
    "env.list",
    "env.stat",
    "env.read",
    "env.find",
    "env.search",
    "env.write",
    "env.mkdir",
    "env.rename",
    "env.remove",
    "env.term.open",
    "env.term.input",
    "env.term.resize",
    "env.term.ack",
    "env.term.close",
    "env.term.list",
    "env.git.status",
    "env.git.diff",
    "env.git.log",
    "env.git.stage",
    "env.git.unstage",
    "env.git.discard",
    "env.git.commit",
    "env.git.snapshots",
    "env.git.rewind",
)

#: Where each side conversation carried on from an earlier run keeps what it was carried on
#: with, by the conversation: taken away as it is closed.
_SCRATCH: dict[int, Path] = {}


def _closed(one: SessionBase) -> None:
    """Closes one side conversation, and takes away what it was carried on with, if anything."""
    with contextlib.suppress(Exception):
        one.close()
    if (scratch := _SCRATCH.pop(id(one), None)) is not None:
        shutil.rmtree(scratch, ignore_errors=True)


def _closed_all(sessions: list[SessionBase]) -> None:
    """Closes side conversations, off whatever thread let go of them."""

    def closes() -> None:
        for one in sessions:
            _closed(one)

    if sessions:
        threading.Thread(target=closes, daemon=True, name="humanize-asides").start()


@dataclasses.dataclass(slots=True, eq=False)
class _Frontend:
    """One frontend attached, and what has been said to it that it has not taken yet."""

    client: str
    name: str
    kind: str
    heard: Callable[[dict[str, Any]], None]
    outbox: collections.deque[tuple[dict[str, Any], int]] = dataclasses.field(
        default_factory=collections.deque[tuple[dict[str, Any], int]]
    )
    ready: threading.Condition = dataclasses.field(default_factory=threading.Condition)
    queued: int = 0
    open: bool = True
    thread: threading.Thread | None = None


@dataclasses.dataclass(slots=True, eq=False)
class _Line:
    """One line said to the run and not taken yet, and the view it was said on."""

    text: str
    by: str
    client: str
    to: str


@dataclasses.dataclass(slots=True, eq=False)
class _Given:
    """One line put into an agent's turn, which the agent has not said it has yet."""

    agent: str
    key: str
    text: str
    by: str
    client: str
    to: str


@dataclasses.dataclass(slots=True, eq=False)
class _Question:
    """One question an `Outworlder` has stopped the run on."""

    id: str
    run: int
    role: str
    text: str
    options: tuple[str, ...]
    mode: str
    key: str = ""
    state: str = "pending"
    answer: str = ""
    #: The JSON Schema its answer is a value of, or None for one answered in text.
    schema: Mapping[str, Any] | None = None
    #: What is shown beside it, as context blocks' JSON forms.
    context: tuple[Mapping[str, Any], ...] = ()
    #: The hash of the face it is answered in, or "" for none.
    face: str = ""
    #: The outworlder session asking, as `<role>/<n>`, or "".
    session: str = ""
    #: What says how a value misfits, as `[{"path", "message"}]`, or None for any fitting.
    check: Callable[[Any], Sequence[Mapping[str, Any]]] | None = None


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class _Shaped:
    """What a question is asked in beyond its text, as `_Question` keeps it."""

    schema: Mapping[str, Any] | None = None
    context: tuple[Mapping[str, Any], ...] = ()
    face: str = ""
    session: str = ""
    check: Callable[[Any], Sequence[Mapping[str, Any]]] | None = None


class _Face(Protocol):
    """A face a flow answers its questions in, as `hmz.flows.Face` is one."""

    @property
    def html(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def hash(self) -> str: ...


@dataclasses.dataclass(slots=True, eq=False)
class _Aside:
    """One side conversation a frontend opened, which only that frontend may turn."""

    side: str
    client: str
    session: SessionBase
    busy: bool = False


@dataclasses.dataclass(slots=True, eq=False)
class _Run:
    """One run this host started, and what the host keeps about it."""

    number: int
    run: Run | Chatting
    started: dict[str, Any]
    numbered: weakref.WeakKeyDictionary[SessionBase, str] = dataclasses.field(
        default_factory=weakref.WeakKeyDictionary[Any, str]
    )
    opened_of: dict[str, int] = dataclasses.field(default_factory=dict[str, int])
    agents: list[AgentBase] = dataclasses.field(default_factory=list[Any])
    working: weakref.WeakSet[SessionBase] = dataclasses.field(
        default_factory=weakref.WeakSet[Any]
    )
    known: dict[str, tuple[AgentBase, SessionBase]] = dataclasses.field(
        default_factory=dict[str, tuple[Any, Any]]
    )
    board: Board | None = None
    stopped_by: str = ""
    #: Of a chat, whether an empty next message was said, which its next wait answers.
    ending: bool = False
    #: The role each session was opened for and where it works, which says whose turn is
    #: open in an environment.
    placed: weakref.WeakKeyDictionary[SessionBase, tuple[str, Placement]] = (
        dataclasses.field(
            default_factory=weakref.WeakKeyDictionary[Any, tuple[str, Any]]
        )
    )


class _Person:
    """The person a chat on a host is had with: whoever is at any frontend attached to it.

    What a chat asks of its person is asked of the host on a thread of its own, the host
    waiting as it does for what a flow asks whoever is outside it.

    Args:
      next: Shows an answer and waits for the next message, "" for none.
      ask: Puts a question with its options and waits for the answer, None for none.
      shell: Shows a `!` command run, with what it printed.
    """

    def __init__(
        self,
        next: Callable[[str], str],  # noqa: A002 -- what the protocol calls it
        ask: Callable[[str, tuple[str, ...]], str | None],
        shell: Callable[[str, str, str, int], None],
    ) -> None:
        self._next = next
        self._ask = ask
        self._shell = shell

    async def next(self, answered: str) -> str:
        """Shows the assistant's answer and waits for the next message; "" ends the chat."""
        import asyncio

        return await asyncio.to_thread(self._next, answered)

    async def ask(self, question: str, options: Sequence[str]) -> str | None:
        """Puts a question the assistant asked mid-turn; None where nobody answers it."""
        import asyncio

        return await asyncio.to_thread(self._ask, question, tuple(options))

    def shell(self, command: str, out: str, err: str, status: int) -> None:
        """Shows a `!` command run for the chat, with what it printed."""
        self._shell(command, out, err, status)


class Host:
    """One workspace's runs, or one chat's, shared by every frontend attached to them."""

    def __init__(self, hmz: Holding, slot: str = "") -> None:
        """Holds the workspace and no run, with nobody attached.

        Args:
          hmz: The workspace, which runs are started in.
          slot: Which of its hosts this is: "" for its own, `chat:<hex>` for a chat's -- which
            folds its chat away once nobody has read it between turns for a while.
        """
        self._hmz = hmz
        self._slot = slot
        #: What names this life of the host, which a frontend that attaches again with
        #: `since` is told its records only where it still names.
        self.epoch = secrets.token_hex(8)
        #: Since when a chat here has been between turns with nobody attached, and whether
        #: it has been folded away for it.
        self._alone: float | None = None
        self._folded = False
        self._lock = threading.RLock()
        #: What a question being waited on waits on, woken whenever a line or an answer
        #: arrives, somebody goes away, or the run it belongs to is over.
        self._spoke = threading.Condition(self._lock)
        self._over = threading.Event()
        self._frontends: dict[str, _Frontend] = {}
        self._clients = itertools.count(1)
        self._history: collections.deque[tuple[dict[str, Any], int]] = (
            collections.deque()
        )
        self._kept = 0
        self._elided = 0
        self._seq = 0
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._claims: dict[str, str] = {}
        self._away_all = False
        self._away_of: dict[str, bool] = {}
        self._current: _Run | None = None
        self._stopping: _Run | None = None
        self._last: _Run | None = None
        #: How the last run to end here ended, for whoever asks from outside the runs.
        self._ended: dict[str, Any] | None = None
        self._runs = 0
        self._starting = False
        self._questions: list[_Question] = []
        self._asking = itertools.count(1)
        self._answered: dict[str, str] = {}
        #: Every face a run here has mounted, by its hash: its HTML and its title.
        self._faces: dict[str, tuple[str, str]] = {}
        self._queue: list[_Line] = []
        self._given: list[_Given] = []
        self._handed = False
        self._asides: dict[str, _Aside] = {}
        self._sides = itertools.count(1)
        self._keeps = False
        self._closed = False
        #: The thread each run started here is driven on, for closing to wait for, and until
        #: when it waits.
        self._driving: list[threading.Thread] = []
        self._letting_go: float | None = None
        self._ticking: threading.Thread | None = None
        self._spent_at = 0.0
        from hmz.runtime.doing.desk import Desk

        self._desk = Desk(
            post=self._post_to, record=self._env_record, guard=self._working_at
        )
        #: Held while the environments are listed, so that a list made before the run
        #: ended never lands after the one made as it did.
        self._listing = threading.Lock()
        self._requests: dict[
            str, Callable[[_Frontend, dict[str, Any]], dict[str, Any]]
        ] = {
            "start": self._start,
            "say": self._say,
            "answer": self._answer,
            "face": self._face,
            "stop": self._stop,
            "force": self._force,
            "afk": self._afk,
            "claim": self._claim,
            "release": self._release,
            "board": self._board,
            "aside": self._aside,
            "unaside": self._unaside,
            "status": lambda _frontend, _said: _ok(**self.status()),
            "detach": self._detach,
            "quit": self._quit,
            # A chat's, said by a frontend here as `chat.*` says them through the daemon.
            "chat.start": functools.partial(self._chats_for, "start"),
            "chat.say": functools.partial(self._chats_for, "say"),
            "chat.commands": functools.partial(self._chats_for, "commands"),
            "chat.set": functools.partial(self._chats_for, "set"),
            "chat.stop": functools.partial(self._chats_for, "stop"),
        }
        for method in _ENV_METHODS:
            self._requests[method] = functools.partial(self._env_asked, method)
        with self._lock:
            self._snap("clients", clients=[])
            self._snap("claims", claims={})
            self._snap("away", all=False, of={})
            self._snap_run()
            self._snap("sessions", run=0, open=[], working=[])
            self._snap("calls", calls=[])
            self._snap_waiting()
            self._snap_pending()
            self._snap("usage", run=0, usage=None, budget=None)
            self._snap("board", items=None)
            self._snap("envs", envs=[])

    # ----------------------------------------------------------------- frontends

    def attach(
        self,
        name: str,
        kind: str,
        heard: Callable[[dict[str, Any]], None],
        *,
        replay: bool = True,
        since: tuple[str, int] | None = None,
    ) -> str:
        """Takes a frontend on, and tells it everything it needs to read the runs from here.

        What it is told first is atomic: who it is, the run so far in order, the state of
        everything as it stands, and `live` -- after which it is told each thing as it happens.
        Told on a thread of its own, never on the caller's and never under a lock, so a
        frontend whose `heard` blocks holds up nothing but itself.

        Args:
          name: What it is called, or "" for whoever is at this end and the kind -- the same
            name twice is told apart with `#2`, `#3` and on.
          kind: What it is: `tui`, `cli` or `sdk`.
          heard: What each message is handed to.
          replay: Whether to be told the run so far, or only what happens from here.
          since: The `epoch` and `seq` of the last record a frontend attaching again was told:
            it is told only those after it where this is the host it was told them by and
            every one after it is still kept, and every record kept otherwise.

        Returns:
          Its client id, which every request of its names it by.

        Raises:
          RuntimeError: If this host has closed.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("this host has closed")
            client = f"c{next(self._clients)}"
            taken = {one.name for one in self._frontends.values()}
            named = wanted = name or f"{_user()}@{kind}"
            for count in itertools.count(2):
                if named not in taken:
                    break
                named = f"{wanted}#{count}"
            frontend = _Frontend(client, named, kind, heard)
            # A finished run kept for one frontend to come and read: this is that one.
            self._keeps = False
            from hmz.rpc import PROTOCOL

            welcome = {
                "type": "welcome",
                "client": client,
                "name": named,
                "kind": kind,
                "workspace": str(self._hmz.workspace),
                "slot": self._slot,
                "pid": os.getpid(),
                "protocol": PROTOCOL,
                "epoch": self.epoch,
            }
            self._post(frontend, welcome, _sized(welcome))
            after = 0
            if since is not None:
                replay = True
                first = self._history[0][0]["seq"] if self._history else self._seq + 1
                epoch, seq = since
                if epoch == self.epoch and first <= seq + 1 <= self._seq + 1:
                    after = seq
            if replay:
                for message, size in self._history:
                    if message["seq"] > after:
                        self._post(frontend, message, size)
            # Everybody else hears of it now, and this one with the rest of the state below.
            self._frontends[client] = frontend
            self._snap_clients(but=client)
            for message in self._snapshots.values():
                self._post(frontend, message, _sized(message))
            live = {"type": "live", "seq": self._seq, "elided": self._elided}
            self._post(frontend, live, _sized(live))
            frontend.thread = threading.Thread(
                target=self._delivers,
                args=(frontend,),
                daemon=True,
                name=f"humanize-frontend-{client}",
            )
            frontend.thread.start()
            self._ticks()
        return client

    def detach(self, client: str) -> None:
        """Lets one frontend go: its claims are given up, and its asides closed.

        Args:
          client: The frontend.
        """
        with self._lock:
            frontend = self._frontends.get(client)
            if frontend is not None:
                self._let_go(frontend, "let go", keep=False)

    @property
    def attached(self) -> int:
        """How many frontends are attached now."""
        with self._lock:
            return len(self._frontends)

    @property
    def idle(self) -> bool:
        """Whether nothing is left for a process holding this to hold it for.

        Nothing running or stopping, nobody attached, and no run that ended with nobody there
        waiting for somebody to come and read it.
        """
        with self._lock:
            return not (
                self._closed
                or self._frontends
                or self._current
                or self._stopping
                or self._starting
                or self._keeps
            )

    @property
    def closed(self) -> bool:
        """Whether this host has been closed."""
        with self._lock:
            return self._closed

    @property
    def epic(self) -> Path | None:
        """The epic of the run in view -- running, else stopping, else the last -- if any."""
        with self._lock:
            shown = self._current or self._stopping or self._last
        return shown.run.epic if shown is not None else None

    def away_for(self, role: str) -> bool:
        """Whether nobody is there to answer as one `Outworlder` role.

        Args:
          role: The role.

        Returns:
          What `/afk` last said of that role, or of every role where nothing was said of it.
        """
        with self._lock:
            return self._away_of.get(role, self._away_all)

    def printed(self, text: str) -> None:
        """Says something printed where the runs are, to every frontend.

        Args:
          text: One line of it.
        """
        with self._lock:
            if not self._closed:
                self._record({"type": "printed", "text": text})

    def asked(self, client: str, said: dict[str, Any]) -> dict[str, Any]:
        """Does what one frontend asked, and answers it.

        Called on whichever thread the frontend asks from, and may take as long as what was
        asked does -- starting a flow imports it, and an aside is a turn.

        Args:
          client: The frontend asking.
          said: The request: `do`, and what that takes.

        Returns:
          `ok`, and `why` where it is not -- a refusal is said in the same words whichever
          frontend asked.
        """
        doing = said.get("do")
        answers = self._requests.get(doing) if isinstance(doing, str) else None
        if answers is None:
            return _no(f"no such request: {doing!r}")
        with self._lock:
            frontend = self._frontends.get(client)
        if frontend is None:
            return _no("this frontend is not attached")
        try:
            return answers(frontend, said)
        except Exception as why:  # noqa: BLE001 -- a request that failed is answered as one
            return _no(str(why) or type(why).__name__)

    def env(self, said: dict[str, Any]) -> dict[str, Any]:
        """Does one `hosts.env.*` on an env of the epic going here, which no frontend asks.

        Carried out through the env's own driver, on the run's loop, as the flow would, and
        neither attaching anybody nor telling the run (Section 4.23 of daemon.md).

        Args:
          said: The call: `do`, its method's whole name, and its params.

        Returns:
          `ok` and the result; or `ok` False, `why`, and the `code` it is refused with.
        """
        from hmz.runtime.doing.envs import NO_FLOW, EnvRefusal, answered

        with self._lock:
            going = self._current or self._stopping
        holds = None
        if going is not None:
            with contextlib.suppress(Exception):
                holds = going.run.envs
        if holds is None:
            return {**_no(NO_FLOW), "code": 409}
        try:
            return _ok(**answered(holds, said))
        except EnvRefusal as why:
            return {**_no(why.why), "code": why.code}
        except Exception as why:  # noqa: BLE001 -- what the env could not do, said as it said it
            return {**_no(str(why) or type(why).__name__), "code": 409}

    def status(self) -> dict[str, Any]:
        """What there is to say about the runs here, for somebody asking from outside them.

        Returns:
          How many frontends are attached and who, the state and number of the run, the
          flow, its epic and task, what it may spend and has spent -- both None with nothing
          running -- the questions it waits on, whether it is a flow's or a chat, the chat
          and where it is in its turn, how the last run to end ended, and the flows running,
          as refs and as calls.
        """
        with self._lock:
            running = self._current
            shown = running or self._stopping or self._last
            clients = self._clients_of()
            state = self._state()
            pending = [
                {
                    "question": one.id,
                    "role": one.role,
                    "text": one.text,
                    "mode": one.mode,
                }
                for one in self._questions
            ]
            ended = dict(self._ended) if self._ended is not None else None
            turn = self._turn(shown)
        calls = self._calls(now=time.monotonic())
        return {
            "attached": len(clients),
            "clients": clients,
            "slot": self._slot,
            "state": state,
            "run": shown.number if shown is not None else 0,
            "epic_kind": shown.run.kind if shown is not None else "",
            "flow": shown.run.flow if shown is not None else "",
            "epic": _epic_of(shown),
            "chat": _epic_of(shown, "chat"),
            "task": shown.started.get("task", "") if shown is not None else "",
            "pending": pending,
            "ended": ended,
            **turn,
            "budget": _json(running.run.budget) if running is not None else None,
            "usage": _json(running.run.usage) if running is not None else None,
            "flows": [one["ref"] for one in calls],
            "calls": calls,
        }

    def close(self) -> None:
        """Closes every run here and lets every frontend go, telling each why.

        And waits a while for those runs to let go of what they made, however many times it is
        called, up to one bound from the first: whoever closes a host may be about to end the
        process holding it, and what a run had not taken down by then -- a container -- would
        outlive it.
        """
        self._close()
        with self._lock:
            driving = list(self._driving)
            # One wait however many times it is closed: from when it first was.
            if self._letting_go is None:
                self._letting_go = time.monotonic() + _LETTING_GO
            until = self._letting_go
        for thread in driving:
            if thread is not threading.current_thread():
                thread.join(max(0.0, until - time.monotonic()))

    def _close(self) -> None:
        """Closes every run here and lets every frontend go, telling each why, once."""
        with self._lock:
            if self._closed:
                return
            runs = [one for one in (self._current, self._stopping) if one is not None]
            for one in runs:
                self._releases(one.number)
            if self._current is not None:
                self._drops(self._current.number, "stopped")
            self._current = self._stopping = None
            self._snap_run()
            sides = [one.session for one in self._asides.values()]
            self._asides.clear()
            frontends = list(self._frontends.values())
            for frontend in frontends:
                self._let_go(frontend, "the host was closed", keep=True)
            self._closed = True
            self._over.set()
            self._spoke.notify_all()
        self._desk.closed()
        for one in runs:
            with contextlib.suppress(Exception):
                one.run.close()
        _closed_all(sides)
        for frontend in frontends:
            thread = frontend.thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=2.0)

    # ------------------------------------------------------------ saying things

    def _delivers(self, frontend: _Frontend) -> None:
        """Hands one frontend what has been said to it, in order, until it is let go."""
        while True:
            with frontend.ready:
                while not frontend.outbox:
                    if not frontend.open:
                        return
                    frontend.ready.wait()
                message, size = frontend.outbox.popleft()
                frontend.queued -= size
            # Outside every lock: a frontend that blocks here is holding up only itself.
            with contextlib.suppress(Exception):
                frontend.heard(message)
            if message.get("type") == "gone":
                return

    def _post(self, frontend: _Frontend, message: dict[str, Any], size: int) -> bool:
        """Puts one message in a frontend's outbox. Whether it is still within its ceiling."""
        with frontend.ready:
            if not frontend.open:
                return True
            frontend.outbox.append((message, size))
            frontend.queued += size
            frontend.ready.notify()
            return frontend.queued <= _BEHIND

    def _broadcast(self, message: dict[str, Any], size: int, but: str = "") -> None:
        """Says one message to every frontend, letting go of any too far behind to take it."""
        behind = [
            frontend
            for client, frontend in list(self._frontends.items())
            if client != but and not self._post(frontend, message, size)
        ]
        for frontend in behind:
            self._let_go(frontend, "too far behind; attach again", keep=False)

    def _record(self, message: dict[str, Any]) -> None:
        """Says one thing that happened, and keeps it for whoever arrives later."""
        self._seq += 1
        kind = message.pop("type")
        written: dict[str, Any] = _clipped(
            {"type": kind, "seq": self._seq, **message}, shows=kind in _SHOWING
        )
        size = _sized(written)
        self._history.append((written, size))
        self._kept += size
        while self._kept > _KEPT and len(self._history) > 1:
            _, gone = self._history.popleft()
            self._kept -= gone
            self._elided += 1
        self._broadcast(written, size)

    def _snap(self, kind: str, /, **fields: Any) -> None:
        """Says how one thing stands now, where that has changed since it was last said."""
        message: dict[str, Any] = _clipped(
            {"type": kind, **fields}, shows=kind in _SHOWING
        )
        if self._snapshots.get(kind) == message:
            return
        self._snapshots[kind] = message
        self._broadcast(message, _sized(message))

    def _let_go(self, frontend: _Frontend, why: str, *, keep: bool) -> None:
        """Takes a frontend off, with its claims and asides, and tells it why last."""
        self._frontends.pop(frontend.client, None)
        with frontend.ready:
            if not frontend.open:
                return
            if not keep:
                frontend.outbox.clear()
                frontend.queued = 0
            frontend.outbox.append(({"type": "gone", "why": why}, 0))
            frontend.open = False
            frontend.ready.notify()
        for role in [
            role for role, one in self._claims.items() if one == frontend.client
        ]:
            del self._claims[role]
        sides = [one for one in self._asides.values() if one.client == frontend.client]
        for one in sides:
            del self._asides[one.side]
        _closed_all([one.session for one in sides])
        # Its terminals live on, for it or anybody to reattach to.
        self._desk.let_go(frontend.client)
        self._snap_clients()
        self._snap_claims()

    def _clients_of(self) -> list[dict[str, str]]:
        return [
            {"client": one.client, "name": one.name, "kind": one.kind}
            for one in self._frontends.values()
        ]

    def _snap_clients(self, but: str = "") -> None:
        message: dict[str, Any] = {"type": "clients", "clients": self._clients_of()}
        if self._snapshots.get("clients") == message:
            return
        self._snapshots["clients"] = message
        self._broadcast(message, _sized(message), but=but)

    def _snap_claims(self) -> None:
        self._snap("claims", claims=dict(self._claims))
        # And who each question waiting is for, which is what a claim changes.
        self._snap_pending()

    def _snap_pending(self) -> None:
        # And the turn of a chat, which a question between turns is the end of.
        self._snap_run()
        self._snap(
            "pending",
            pending=[
                {
                    "question": one.id,
                    "run": one.run,
                    "role": one.role,
                    "text": one.text,
                    "options": list(one.options),
                    "mode": one.mode,
                    "key": one.key,
                    "owner": self._claims.get(one.role),
                    **self._shaped(one),
                }
                for one in self._questions
            ],
        )

    def _snap_waiting(self) -> None:
        self._snap(
            "waiting",
            queued=[
                {"text": one.text, "by": one.by, "client": one.client, "to": one.to}
                for one in self._queue
            ],
            given=[
                {
                    "agent": one.agent,
                    "text": one.text,
                    "by": one.by,
                    "client": one.client,
                }
                for one in self._given
            ],
        )

    def _state(self) -> str:
        if self._current is not None:
            return "running"
        return "stopping" if self._stopping is not None else "idle"

    def _snap_run(self) -> None:
        shown = self._current or self._last
        self._snap(
            "run",
            state=self._state(),
            **(shown.started if shown is not None else {"run": 0}),
            stopping=self._stopping.number if self._stopping is not None else None,
            # Which epic it writes, or which chat, once it has one: what a frontend
            # addresses it by.
            epic=_epic_of(shown),
            chat=_epic_of(shown, "chat"),
            slot=self._slot,
            **self._turn(shown),
        )

    def _turn(self, shown: _Run | None) -> dict[str, str]:
        """Where a chat is in its turn: "running" while its agent answers, "done" otherwise.

        A turn ends where the chat asks what to say next, or where the chat does; what the
        agent asks its user mid-turn is not the end of one, and a `!` command or a line
        refused between two turns is not the start of one. Nothing for an epic of a flow.
        Under the lock.
        """
        if shown is None or shown.run.kind != "chat":
            return {}
        between = shown is not self._current or shown.run.chat.between
        listening = any(
            one.run == shown.number and one.mode == "listen" for one in self._questions
        )
        return {"turn": "done" if between or listening else "running"}

    def _name_of(self, client: str) -> str:
        frontend = self._frontends.get(client)
        return frontend.name if frontend is not None else client

    def _may(self, client: str, role: str) -> bool:
        """Whether a frontend may speak for a role: its claimant, or anybody's if unclaimed."""
        return self._claims.get(role) in (None, client)

    # ------------------------------------------------------------------ the tick

    def _ticks(self) -> None:
        """Starts looking at what nothing announces, the once."""
        if self._ticking is None:
            self._ticking = threading.Thread(
                target=self._looks, daemon=True, name="humanize-host"
            )
            self._ticking.start()

    def _looks(self) -> None:
        """Says what is open, what is running and what it spent, as it changes."""
        while not self._over.wait(_TICK):
            with contextlib.suppress(Exception):
                self._polls()

    def _polls(self) -> None:
        calls = self._calls()
        with self._lock:
            shown = self._current or self._stopping or self._last
            running = self._current
            self._snap_sessions(shown)
        spent: dict[str, Any] | None = None
        now = time.monotonic()
        if running is not None and now - self._spent_at >= _SPENDING:
            self._spent_at = now
            spent = {
                "run": running.number,
                "usage": _json(running.run.usage),
                "budget": _json(running.run.budget),
            }
        with self._lock:
            self._snap("calls", calls=calls)
            if spent is not None and self._current is running:
                self._snap("usage", **spent)
            # The epic is named a moment after the run starts, and nothing announces it.
            self._snap_run()
            self._folds()
        # What the run holds changes as its flow derives and destroys, unannounced.
        self._lists_envs()
        self._desk.tick()

    def _folds(self) -> None:
        """Folds a chat away that has been between turns with nobody attached for long enough.

        Folded as an empty next message ends it: everybody away, so the question it waits on
        is answered with nothing and the chat returns, keeping its conversation. Only a chat's
        own host does. Under the lock.
        """
        current = self._current
        if (
            not self._slot
            or self._folded
            or current is None
            or current.run.kind != "chat"
            or self._frontends
            or self._turn(current).get("turn") != "done"
        ):
            self._alone = None
            return
        now = time.monotonic()
        if self._alone is None:
            self._alone = now
        if now - self._alone < FOLD:
            return
        self._folded = True
        self._away_all = True
        self._away_of.clear()
        self._goes_away()

    def _calls(self, now: float | None = None) -> list[dict[str, Any]]:
        """Every flow call going here, oldest first: since when, or how long for `now`."""
        try:
            running = self._hmz.flows.running()
        except Exception:  # noqa: BLE001 -- a tree nobody could read is no flows at all
            return []
        at = {id(one): index for index, one in enumerate(running)}
        return [
            {
                "ref": one.ref,
                "name": one.name,
                "depth": one.depth,
                **(
                    {"since": one.since}
                    if now is None
                    else {"seconds": round(now - one.since, 3)}
                ),
                "id": one.id,
                "parent": None if one.parent is None else at.get(id(one.parent)),
            }
            for one in running
        ]

    def _snap_sessions(self, shown: _Run | None) -> None:
        if shown is None:
            self._snap("sessions", run=0, open=[], working=[])
            return
        still = {id(one) for one in shown.run.agents}
        held = [
            (agent, session, key)
            for agent in dict.fromkeys(shown.agents)
            for session in agent.sessions
            if (key := shown.numbered.get(session)) is not None
        ]
        self._snap(
            "sessions",
            run=shown.number,
            open=[key for agent, _, key in held if id(agent) in still],
            working=[key for _, session, key in held if session in shown.working],
        )

    # ---------------------------------------------------------------------- runs

    def _start(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        flow = said.get("flow")
        if not isinstance(flow, str) or not flow:
            return _no("a flow to start is named")
        task = str(said.get("task") or "")
        agents: Mapping[str, Any] = said.get("agents") or {}
        envs: Mapping[str, Any] = said.get("envs") or {}
        params = said.get("params")
        resume = said.get("resume") or False
        backup = said.get("backup")
        if backup is not None and not (
            isinstance(backup, list) and all(isinstance(one, str) for one in backup)  # pyright: ignore[reportUnknownVariableType]
        ):
            return _no("backup is a list of backup target names")
        with self._lock:
            if self._closed:
                return _no("this host has closed")
            if self._slot.startswith("chat:"):
                return _no("a chat is started with chat.start")
            if self._current is not None:
                return _no("a flow is already running")
            if self._starting:
                return _no("a flow is already starting")
            if self._slot.startswith("exec:") and self._runs:
                return _no("an exec host runs one epic")
            self._starting = True
            number = self._runs + 1
        try:
            from hmz.runtime.flowing import open_outworlder

            run = self._hmz.run(
                flow,
                task,
                agents=agents,
                envs=envs,
                params=params,
                budget=said.get("budget"),
                profile_flow=bool(said.get("profile_flow")),
                profile_environment=bool(said.get("profile_environment")),
                resume=resume,
                backup=cast("list[str] | None", backup),
                # Whoever is outside the run is every frontend here: asked on a thread of
                # the run's own, and away while `/afk` says so.
                outworlder=open_outworlder(
                    ask=functools.partial(self._asks, number),
                    away=self.away_for,
                    show=functools.partial(self._shows, number),
                    faces=self._mounts,
                ),
            )
            declared = run.declaration
            started: dict[str, Any] = {
                "run": number,
                "kind": run.kind,
                "flow": flow,
                "ref": run.ref,
                "task": task,
                "by": frontend.name,
                "client": frontend.client,
                "roles": [one.name for one in declared.agents if not one.auto],
                # What the agent filling each is called, which its sessions are keyed by:
                # the role is only the parameter it is taken as.
                "names": run.names,
                "outworlders": [one.name for one in declared.agents if one.auto],
                "agents": _spoken(agents) if isinstance(agents, dict) else {},
                "envs": _spoken(envs) if isinstance(envs, dict) else {},
                "params": dict(params) if isinstance(params, dict) else {},  # pyright: ignore[reportUnknownArgumentType]
                "budget": _json(run.budget),
                "profile_flow": run.profile_flow,
                "profile_environment": run.profile_environment,
                "backup": list(run.backup),
                "resume": str(resume) if resume else "",
                "began": time.monotonic(),
                "at": time.time(),
            }
        except Exception as why:  # noqa: BLE001 -- a flow that will not start is a line to fix
            with self._lock:
                self._starting = False
            return _no(str(why) or type(why).__name__)
        if not self._begins(_Run(number, run, started)):
            return _no("this host has closed")
        return _ok(run=number)

    def _begins(self, current: _Run) -> bool:
        """Takes on an epic made to start, and starts it. Whether it was, the host still open."""
        number, run, started = current.number, current.run, current.started
        with self._lock:
            self._starting = False
            if self._closed:
                # Closed while the flow was loading: nothing of it is started.
                return False
            self._runs = number
            self._current = self._last = current
            self._keeps = False
            # One run's history: a frontend arriving now reads this run, not the last.
            self._history.clear()
            self._kept = self._elided = 0
            self._queue.clear()
            self._given.clear()
            self._handed = False
            # A side conversation is about the run it was opened on, and that run has gone.
            sides = [one.session for one in self._asides.values()]
            self._asides.clear()
            self._record({"type": "started", **started})
            self._snap_run()
            self._snap_sessions(current)
            self._snap_waiting()
            self._snap("board", items=None)
            self._snap("usage", run=number, usage=None, budget=started["budget"])
            self._ticks()
        _closed_all(sides)
        self._lists_envs()
        run.watch(functools.partial(self._heard, current))
        run.opened(functools.partial(self._opened, current))
        run.noticed(functools.partial(self._noticed, current))
        driving = threading.Thread(
            target=self._drives, args=(current,), daemon=True, name="humanize-run"
        )
        with self._lock:
            self._driving = [one for one in self._driving if one.is_alive()]
            self._driving.append(driving)
        driving.start()
        return True

    # --------------------------------------------------------------------- chats

    def chatted(self, said: dict[str, Any]) -> dict[str, Any]:
        """Does what was asked of the chat here from outside every frontend, and answers it.

        What `chat.*` of daemon.md asks, through the daemon: nobody attached says it, so it is
        said by whoever the daemon names.

        Args:
          said: `do` -- `start`, `say`, `commands`, `set` or `stop` -- what that takes, and
            `by`, who asked.

        Returns:
          `ok`, and `why` and `code` where it is not.
        """
        return self._chats(
            str(said.get("do") or ""), str(said.get("by") or ""), "", said
        )

    def _chats_for(
        self, do: str, frontend: _Frontend, said: dict[str, Any]
    ) -> dict[str, Any]:
        return self._chats(do, frontend.name, frontend.client, said)

    def _chats(
        self, do: str, by: str, client: str, said: dict[str, Any]
    ) -> dict[str, Any]:
        doing = {
            "start": self._chat_start,
            "say": self._chat_say,
            "commands": self._chat_commands,
            "set": self._chat_set,
            "stop": self._chat_stop,
        }.get(do)
        if doing is None:
            return _no(f"no such request: chat.{do}")
        try:
            return doing(by, client, said)
        except Exception as why:  # noqa: BLE001 -- a request that failed is answered as one
            return _no(str(why) or type(why).__name__)

    def _chat_start(self, by: str, client: str, said: dict[str, Any]) -> dict[str, Any]:
        """Starts a chat here, or carries one on, and answers it with its slot and its name."""
        checked = chat_checked(self._hmz, said)
        if not checked["ok"]:
            return checked
        agent, task, resume = checked["agent"], checked["task"], checked["resume"]
        # The chat carried on, by its name, as whoever follows this host is told of it.
        resumed = Path(resume).name if resume else None
        prefer: Prefer | None = checked["prefer"]
        ai = self._slot.startswith("ai:")
        if ai and (client or not isinstance(said.get("ai"), dict)):
            # Her conversation is the daemon's to start, with the reach it keeps for it.
            return _no("an Ai-chan host has her own conversation", 409)
        with self._lock:
            if self._closed:
                return _no("this host has closed", 409)
            if not self._slot.startswith(("chat:", "ai:")):
                return _no(f"{self._slot or 'the workspace'} is not a chat slot.", 400)
            if self._folded:
                return _no(_FOLDED, 409)
            if self._current is not None or self._starting or self._runs:
                return _no(f"a chat is already going on {self._slot}", 409)
            self._starting = True
            number = self._runs + 1
        person = _Person(
            functools.partial(self._next_line, number),
            functools.partial(self._puts, number),
            functools.partial(self._shelled, number),
        )
        try:
            # An Ai-chan conversation: a chat whose assistant plays her role, held to the
            # reach it was made with (Section 14 of core.md).
            role = _her(said) if ai else None
            run = self._hmz.chat(
                agent,
                task,
                person=person,
                resume=resume or None,
                prefer=prefer,
                role=role,
                permission=None if ai else checked["permission"],
                worktree=checked["worktree"],
            )
        except Exception as why:  # noqa: BLE001 -- a chat that will not start is said so
            with self._lock:
                self._starting = False
            return _no(str(why) or type(why).__name__, 400)
        started: dict[str, Any] = {
            "run": number,
            "kind": run.kind,
            "flow": "",
            "ref": "",
            "task": task,
            "by": by,
            "client": client,
            "roles": ["assistant"],
            "names": {},
            "outworlders": [],
            "agents": {"assistant": agent},
            "envs": {},
            "params": None,
            "budget": None,
            "profile_flow": False,
            "profile_environment": False,
            "backup": [],
            "resume": resumed,
            "began": time.monotonic(),
            "at": time.time(),
        }
        current = _Run(number, run, started)
        if not self._begins(current):
            return _no("this host has closed", 409)
        answer = self._named(current, run)
        if answer["ok"] and said.get("remember") is True:
            from hmz.runtime.settings import Settings

            # Once the start is taken, so that one refused leaves the agent there was.
            Settings(self._hmz.workspace).chat_agent = checked["runs"]
        return answer if not answer["ok"] else answer | {"slot": self._slot}

    def _named(self, current: _Run, run: Chatting) -> dict[str, Any]:
        """A chat started, answered with its name once it has one, or how it ended without.

        A chat that is refused -- an agent it cannot open -- ends before its record is made,
        and its start is refused with why (Section 8.3.7 of core.md).
        """
        deadline = time.monotonic() + (_NAMING if run.names_epic else 0.0)
        with self._lock:
            while True:
                epic = run.epic
                if epic is not None:
                    return _ok(run=current.number, chat=epic.name)
                ended = self._ended
                if self._current is not current and (
                    ended is not None and ended.get("run") == current.number
                ):
                    if ended.get("how") in ("refused", "failed", "crashed"):
                        why = str(ended.get("why") or "").strip()
                        return _no(why.splitlines()[-1] if why else "it failed", 400)
                    return _ok(run=current.number, chat="")
                left = deadline - time.monotonic()
                if left <= 0:
                    return _ok(run=current.number, chat="")
                self._spoke.wait(min(left, _TICK / 5))

    def _chatting(self) -> tuple[_Run, Chatting] | dict[str, Any]:
        """The chat going here, or why there is none to say anything to. Under the lock."""
        if self._folded:
            return _no(_FOLDED, 409)
        current = self._current
        if current is None or current.run.kind != "chat":
            if self._slot.startswith("chat:") and self._runs:
                return _no(_ENDED, 409)
            return _no("no chat is going here", 409)
        return current, current.run

    def _chat_say(self, by: str, client: str, said: dict[str, Any]) -> dict[str, Any]:
        """Says one line to the chat: the next message, an answer, or the end of it."""
        from hmz.runtime.chatting import resolve

        text = said.get("text")
        if not isinstance(text, str):
            return _no("a line is text", 400)
        with self._lock:
            going = self._chatting()
        if isinstance(going, dict):
            return going
        current, run = going
        line = text.strip()
        if not line:
            return self._chat_ends(current, by, client)
        # Only what a line's sigil asks for is read: prose is said, and only a `$` names a flow.
        sigiled, named = line[0] in "/$!@", line[0] == "$"
        read = resolve(
            line,
            catalog=_natives(run) if sigiled else [],
            flows=self._flow_names() if named else (),
            prefer=self._prefer(run) if named else "native",
            listed=run.chat.listed,
        )
        # Named as typed: the sigil and the name, or the line where it is one of `!` or `@`.
        typed = line if line[0] in "!@" else line.split(maxsplit=1)[0]
        if read.kind == "reserved":
            return _no(f"{typed} is served by the frontend, not said to the chat", 400)
        if read.kind == "flow":
            return _no(f"{typed} names a flow, which the frontend starts", 400)
        if read.kind == "refused":
            return _no(f"{typed} cannot be said here: {read.why}", 400)
        with self._lock:
            if self._current is not current:
                return _no(_ENDED, 409)
            # What the assistant asked mid-turn is answered by the next thing said.
            asked = next(
                (
                    one
                    for one in self._questions
                    if one.run == current.number and one.mode == "ask"
                ),
                None,
            )
            if asked is not None:
                self._answers(asked, _chosen(asked.options, text), by, client)
                return _ok()
            # A native line is a turn of its own, and never words put into the turn open.
            to = _NATIVE if read.kind == "native" else ""
            self._queue.append(_Line(text, by, client, to))
            self._snap_waiting()
            self._spoke.notify_all()
        self._hand_over()
        return _ok()

    def _chat_ends(self, current: _Run, by: str, client: str) -> dict[str, Any]:
        """Ends a chat as an empty next message does: now between turns, else after this one."""
        with self._lock:
            current.ending = True
            for asked in [
                one
                for one in self._questions
                if one.run == current.number and one.mode == "listen"
            ]:
                self._answers(asked, "", by, client)
            self._spoke.notify_all()
        return _ok()

    def _chat_commands(
        self, by: str, client: str, said: dict[str, Any]
    ) -> dict[str, Any]:
        """What a line of the chat here can start with, and what its `$` names prefer."""
        del by, client, said
        from hmz.runtime.chatting import RESERVED

        with self._lock:
            going = self._chatting()
        if isinstance(going, dict):
            return going
        _, run = going
        entries: list[dict[str, Any]] = [
            {
                "sigil": one.sigil,
                "name": one.name,
                "about": one.about,
                "how": one.how,
                "source": "native",
            }
            for one in _natives(run)
        ]
        entries += [
            {"sigil": "/", "name": name, "about": "", "how": "", "source": "hmz"}
            for name in sorted(RESERVED)
        ]
        entries += [
            {
                "sigil": "$",
                "name": one.name,
                "about": one.about,
                "how": "",
                "source": "flow",
            }
            for one in self._flows()
        ]
        own = run.chat.prefer
        return _ok(
            entries=entries,
            prefer=self._prefer(run),
            prefer_from="settings" if own is None else "chat",
            permission=run.chat.permission,
            listed=run.chat.listed,
        )

    def _chat_set(self, by: str, client: str, said: dict[str, Any]) -> dict[str, Any]:
        """Sets the chat's own preference, its permission, or both, recorded in the chat."""
        del by, client
        refused = chat_set_refused(said)
        if refused:
            return _no(refused, 400)
        with self._lock:
            going = self._chatting()
        if isinstance(going, dict):
            return going
        chat = going[1].chat
        if said.get("permission") is not None:
            if chat.permission is None:
                return _no("an Ai-chan conversation keeps its permission", 409)
            chat.permits(said["permission"])
        if said.get("prefer") is not None:
            chat.prefers(said["prefer"])
        return _ok()

    def _chat_stop(self, by: str, client: str, said: dict[str, Any]) -> dict[str, Any]:
        """Stops the chat's open turn, leaving it between turns (Section 8.5.4 of core.md)."""
        del by, client, said
        with self._lock:
            going = self._chatting()
        if isinstance(going, dict):
            return going
        if not going[1].interrupt():
            # Her conversation's, as its own frontends word it (Section 4.22.5.3).
            ai = self._slot.startswith("ai:")
            return _no(
                "Ai-chan is not answering, so there is nothing to stop"
                if ai
                else _NO_TURN,
                409,
            )
        return _ok()

    def _flows(self) -> list[Any]:
        """The flows on offer in this workspace, or none where they cannot be read."""
        try:
            return list(self._hmz.flows.all())
        except Exception:  # noqa: BLE001 -- flows nobody could read are no flows to name
            return []

    def _flow_names(self) -> set[str]:
        return {str(one.name) for one in self._flows()}

    def _prefer(self, run: Chatting) -> Prefer:
        """What `$<name>` means in a chat where it is both: its own say, else the setting."""
        own = run.chat.prefer
        if own is not None:
            return own
        from hmz.runtime.settings import Settings

        # Read afresh: the setting is the person's to change while the chat goes on.
        return Settings(self._hmz.workspace).chat_prefer

    def _next_line(self, number: int, answered: str) -> str:
        """What a chat is said next, waited for: "" where it is over or nobody is there."""
        return self._waits(number, _PERSON, answered, (), "listen") or ""

    def _puts(self, number: int, question: str, options: tuple[str, ...]) -> str | None:
        """What a chat's assistant asks mid-turn, put to the person and waited on."""
        return self._waits(number, _PERSON, question, options, "ask")

    def _shelled(
        self, number: int, command: str, out: str, err: str, status: int
    ) -> None:
        """Says a `!` command run for a chat, and what it printed, where every frontend reads it."""
        with self._lock:
            current = self._current
            if self._closed or current is None or current.number != number:
                return
            keys = list(current.numbered.values())
            self._record(
                {
                    "type": "shell",
                    "run": number,
                    "key": keys[-1] if keys else "",
                    "command": command,
                    "out": out,
                    "err": err,
                    "status": status,
                }
            )

    def _drives(self, current: _Run) -> None:
        """Runs one flow -- or has one chat -- to its end, and says how it ended.

        A chat ends `stopped` however it is left, short of failing (Section 8.5.3 of
        core.md): what it returns says which.
        """
        import asyncio
        import traceback

        from hmz.coganchor.agents import Stopped
        from hmz.flows import BudgetExceeded, FlowException
        from hmz.runtime import telemetry
        from hmz.runtime.chatting import ChatEnd
        from hmz.runtime.runner import Refused

        how, why, result = "done", "", None
        try:
            # Said where every frontend reads it, as a command line says it on its stderr.
            if blind := current.run.unreadable():
                with self._lock:
                    if not self._closed:
                        self._record(
                            {"type": "notice", "run": current.number, "text": blind}
                        )
            returned = current.run.run()
            if isinstance(returned, ChatEnd):
                how, why = returned.state, returned.why
            else:
                result = _returned(returned)
        except (asyncio.CancelledError, Stopped):
            how = "stopped"
        except Refused as refused:
            how, why = "refused", str(refused)
        except BudgetExceeded as over:
            # The ordinary end of a budgeted loop rather than a crash.
            how, why = "budget", str(over)
        except FlowException as failed:
            how, why = "failed", f"{type(failed).__name__}: {failed}"
        except BaseException as crashed:  # noqa: BLE001 -- said, and reported, rather than lost
            telemetry.crash(crashed, doing=f"a {current.run.kind}")
            how, why = "crashed", traceback.format_exc().strip()
        spent: dict[str, Any] | None = None
        with contextlib.suppress(Exception):
            spent = {
                "run": current.number,
                "usage": _json(current.run.usage),
                "budget": _json(current.run.budget),
            }
        with self._lock:
            if self._stopping is current:
                self._stopping = None
            if self._current is current:
                self._current = None
                self._releases(current.number)
                self._drops(current.number, "ended")
                # Nobody was there to see it end, and nobody asked for it to: the next to
                # arrive is the one it ended for. A chat ends only as somebody leaves it,
                # its conversation kept in the chat, and so for nobody; an exec host's one
                # epic is not kept either, for nothing attaches to that host again.
                if (
                    not self._frontends
                    and not current.stopped_by
                    and current.run.kind != "chat"
                    and not self._slot.startswith("exec:")
                ):
                    self._keeps = True
            self._ended = {
                "how": how,
                "why": why,
                "epic": _epic_of(current),
                "chat": _epic_of(current, "chat"),
                "at": time.time(),
                "run": current.number,
                "kind": current.run.kind,
                "flow": current.run.flow,
                "task": current.started.get("task", ""),
            }
            self._record(
                {
                    "type": "ended",
                    "run": current.number,
                    "how": how,
                    "why": why,
                    "mono": time.monotonic(),
                    "result": result,
                }
            )
            self._snap_run()
            self._snap_sessions(self._current or self._stopping or current)
            if self._last is current and spent is not None:
                self._snap("usage", **spent)
            self._spoke.notify_all()
        self._lists_envs()

    def _stop(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del said
        with self._lock:
            current = self._current
            if current is not None and current.run.kind == "chat":
                # A chat's open turn alone: the chat goes on between turns (Section 8.5.4 of
                # core.md), as `chat.stop` leaves it.
                return self._chat_stop(frontend.name, frontend.client, {})
            if current is None:
                if self._stopping is not None:
                    return _no(f"the flow is already stopping: {_UNWINDING}")
                return _no("no flow is running, so there is nothing to stop")
            self._stops(current, frontend)
        current.run.stop()
        return _ok()

    def _stops(self, current: _Run, by: _Frontend) -> None:
        """Takes a run off as the one going, as stopping it does. Under the lock."""
        self._current = None
        self._stopping = current
        current.stopped_by = by.name
        self._record(
            {
                "type": "stopping",
                "run": current.number,
                "by": by.name,
                "client": by.client,
            }
        )
        self._releases(current.number)
        self._drops(current.number, "stopped")
        self._snap_run()
        self._spoke.notify_all()

    def _force(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del said
        with self._lock:
            current = self._current
            if current is not None:
                self._stops(current, frontend)
            stopping = self._stopping
            if stopping is None:
                return _no("no flow is running, so there is nothing to stop")
            closing = [
                session
                for agent in dict.fromkeys(stopping.agents)
                for session in agent.sessions
                if session in stopping.working
            ]
            # It reads as over from here, whatever is still unwinding behind it.
            self._stopping = None
            self._snap_run()
        if current is not None:
            current.run.stop()
        stopping.run.close()
        with self._lock:
            for session in closing:
                stopping.working.discard(session)
            self._snap_sessions(self._current or stopping)
        self._lists_envs()
        return _ok(closed=len(closing))

    def _quit(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del frontend, said
        self.close()
        return _ok()

    def _detach(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del said
        self.detach(frontend.client)
        return _ok()

    # -------------------------------------------------------------- environments

    def _lists_envs(self) -> None:
        """Says the environments of the run in view as they stand. Not under the lock."""
        with self._listing:
            with self._lock:
                shown = self._current or self._stopping or self._last
                going = shown is not None and shown in (self._current, self._stopping)
            if shown is None:
                return
            holds = None
            if going:
                with contextlib.suppress(Exception):
                    holds = shown.run.envs
            envs = self._desk.refresh(shown.number, holds, going=going)
            with self._lock:
                if not self._closed:
                    self._snap("envs", envs=envs)

    def _env_asked(
        self, method: str, frontend: _Frontend, said: dict[str, Any]
    ) -> dict[str, Any]:
        return _ok(**self._desk.asked(frontend.client, frontend.name, method, said))

    def _post_to(self, client: str, message: dict[str, Any]) -> None:
        """Says one message to one frontend alone: what a terminal it watches printed."""
        frontend = self._frontends.get(client)
        if frontend is not None:
            self._post(frontend, message, _sized(message))

    def _env_record(self, message: dict[str, Any]) -> None:
        """Writes what a frontend did in an environment into the run's history."""
        with self._lock:
            if not self._closed:
                self._record(message)

    def _working_at(self, run: int, driver: Any) -> str | None:
        """The role of a session with a turn open where a driver works, if any."""
        with self._lock:
            for shown in (self._current, self._stopping):
                if shown is None or shown.number != run:
                    continue
                for session in list(shown.working):
                    placed = shown.placed.get(session)
                    if placed is not None and _works_at(placed[1], driver):
                        return placed[0]
        return None

    # ---------------------------------------------------------------- what opened

    def _noticed(self, current: _Run, said: str) -> None:
        """Says Humanize's own word about the run where every frontend reads it.

        An environment moved off the runtime its `-e` named, as `hmz exec` says it on its
        stderr.
        """
        with self._lock:
            if not self._closed:
                self._record({"type": "notice", "run": current.number, "text": said})

    def _opened(
        self,
        current: _Run,
        role: str,
        agent: AgentBase,
        session: SessionBase,
        where: Placement | None = None,
    ) -> None:
        """Takes one session the run opened as one of its own, before its first turn."""
        from hmz.coganchor.agents import HumanAgent
        from hmz.runtime.epic import harnessed

        person = isinstance(agent, HumanAgent)
        board: Board | None = None
        with self._lock:
            # Numbered now, in the order the run opens them, rather than as each first
            # speaks: `NeiKos496/2` is the second conversation NeiKos496 opened, whichever
            # role it fills.
            key = self._key_of(current, agent, session)
            current.agents.append(agent)
            if where is not None:
                current.placed[session] = (role, where)
            if person:
                if current.board is None:
                    board = current.board = agent.board
            else:
                current.known[key] = (agent, session)
                while len(current.known) > _SIDES:
                    del current.known[next(iter(current.known))]
            forks = False
            with contextlib.suppress(Exception):
                forks = bool(session.forks)
            # Where its harness was put, for work on another machine: the one thing about
            # a session that was settled as it opened rather than written on the line.
            machine = None if person else agent.config.machine
            kept = None if person else agent.kept()
            self._record(
                {
                    "type": "opened",
                    "run": current.number,
                    "role": role,
                    "key": key,
                    "agent": agent.id,
                    "cli": agent.backend,
                    "model": agent.config.model,
                    "counts": sorted(type(agent).counts),
                    "forks": forks,
                    "person": person,
                    "kept": "" if kept is None else str(kept),
                    "env": _placed(where),
                    "harness": "" if machine is None else harnessed(machine),
                    "mono": time.monotonic(),
                    # And on the wall, which is the clock the CLIs write their logs on: a
                    # row written before this is not one this run's session spent.
                    "wall": time.time(),
                }
            )
            self._snap_sessions(current)
            if board is not None:
                self._snap_board(board)
        # Whichever turn of it starts next folds in the oldest line waiting for it.
        agent.waiting = functools.partial(self._at_turn_start, current, agent, session)
        if board is not None:
            board.watch(functools.partial(self._boarded, current))

    def _key_of(
        self, current: _Run, agent: AgentBase, session: SessionBase | None
    ) -> str:
        """The transcript a conversation's lines go on, numbering it the first time.

        What no one conversation said goes on the one working, or the newest, and on the agent
        alone where it has none. Under the lock.
        """
        if session is None:
            session = self._working_in(current, agent) or next(
                reversed(agent.sessions), None
            )
        if session is None:
            return agent.id
        key = current.numbered.get(session)
        if key is None:
            counted = current.opened_of[agent.id] = (
                current.opened_of.get(agent.id, 0) + 1
            )
            key = current.numbered[session] = f"{agent.id}/{counted}"
        return key

    @staticmethod
    def _working_in(current: _Run, agent: AgentBase) -> SessionBase | None:
        from hmz.coganchor.agents import HumanAgent

        if isinstance(agent, HumanAgent):
            return None
        working = [one for one in agent.sessions if one in current.working]
        return working[-1] if working else None

    def _heard(
        self,
        current: _Run,
        agent: AgentBase,
        session: SessionBase | None,
        event: Event,
    ) -> None:
        """Says one thing a turn said, and keeps up what it means for the lines waiting."""
        handing = False
        with self._lock:
            key = self._key_of(current, agent, session)
            if event.kind == "begins" and session is not None:
                current.working.add(session)
            self._record(record(agent, session, event, key=key, run=current.number))
            # What is waiting is the run going now's, and a run on its way out has none.
            ours = current is self._current
            if event.kind == "begins":
                self._snap_sessions(current)
                handing = ours
            elif event.kind == "ends":
                if session is not None:
                    current.working.discard(session)
                if ours:
                    self._unholds(current, agent)
                self._snap_sessions(current)
            elif event.kind == "took" and ours:
                handing = self._took(current, agent, key, event.text)
        if handing:
            self._hand_over()

    # ------------------------------------------------------------------- lines

    def _say(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        if self._slot.startswith("chat:"):
            return _no(_TO_CHAT)
        text = said.get("text")
        if not isinstance(text, str) or not text:
            return _no("a line says something")
        to = str(said.get("to") or "")
        with self._lock:
            if self._current is None:
                return _no("no flow is running to say it to")
            if to.startswith(_OUTWORLDER):
                role = to.removeprefix(_OUTWORLDER)
                if not self._may(frontend.client, role):
                    return _no(f"{role} is {self._name_of(self._claims[role])}'s")
            self._queue.append(_Line(text, frontend.name, frontend.client, to))
            self._snap_waiting()
            # A flow between turns is waiting to be told something.
            self._spoke.notify_all()
        self._hand_over()
        return _ok()

    def _at_turn_start(
        self, current: _Run, agent: AgentBase, session: SessionBase
    ) -> list[str]:
        """What a turn starting folds into its prompt: the oldest line for it, or none.

        None where the run asking is no longer the one going -- a stopping run's agents take
        nothing meant for the run that replaced it. And where the person has just answered
        what to say next, which this turn is already about, none said to the run at large:
        each of those waits to be a turn of its own. A line said to this agent or this
        conversation by name is still for the next turn it takes, which is this one.
        """
        with self._lock:
            if current is not self._current:
                return []
            key = current.numbered.get(session, agent.id)
            wanted = (agent.id, key) if self._handed else ("", agent.id, key)
            self._handed = False
            line = next((one for one in self._queue if one.to in wanted), None)
            if line is None:
                return []
            self._queue.remove(line)
            self._record(
                {
                    "type": "said",
                    "run": current.number,
                    "text": line.text,
                    "key": key,
                    "by": line.by,
                    "client": line.client,
                }
            )
            self._snap_waiting()
        return [line.text]

    def _hand_over(self) -> None:
        """Puts the oldest line for each target into its turn, one per agent at a time.

        A line goes only into a conversation with a turn open -- one written between turns
        is answered on its own, outside the flow -- and only to an agent that has said it has
        the last one: a backend given a second word while swallowing the first answers once.
        And one per agent each time this is asked: a word the agent refuses goes back to the
        head of the queue, and is tried again when something next moves rather than at once.
        """
        handed: set[str] = set()
        while True:
            with self._lock:
                current = self._current
                if current is None:
                    return
                picked = self._picks(current, handed)
                if picked is None:
                    return
                line, agent, session, key = picked
                handed.add(agent.id)
                self._queue.remove(line)
                given = _Given(agent.id, key, line.text, line.by, line.client, line.to)
                self._given.append(given)
                self._snap_waiting()
            # Off every lock, and off the thread that asked: this writes to the agent.
            threading.Thread(
                target=self._puts_in,
                args=(current, given, session),
                daemon=True,
                name="humanize-steer",
            ).start()

    def _picks(
        self, current: _Run, handed: set[str]
    ) -> tuple[_Line, AgentBase, SessionBase, str] | None:
        holding = {one.agent for one in self._given} | handed
        tried: set[str] = set()
        for line in self._queue:
            if line.to in tried or line.to.startswith(_OUTWORLDER):
                continue
            tried.add(line.to)
            found = self._target(current, line.to)
            if found is None or found[0].id in holding:
                continue
            agent, session = found
            return line, agent, session, current.numbered.get(session, agent.id)
        return None

    @staticmethod
    def _target(current: _Run, to: str) -> tuple[AgentBase, SessionBase] | None:
        """The conversation a line said on one view goes into, where one is working.

        A conversation's own view is that conversation; an agent's is its newest working one;
        and every agent's is the first working one in the order the flow opened them.
        """
        from hmz.coganchor.agents import HumanAgent

        working = [
            (agent, session)
            for agent in dict.fromkeys(current.agents)
            if not isinstance(agent, HumanAgent)
            for session in agent.sessions
            if session in current.working
        ]
        if not to:
            return working[0] if working else None
        if "/" in to:
            return next(
                (one for one in working if current.numbered.get(one[1]) == to), None
            )
        held = [one for one in working if one[0].id == to]
        return held[-1] if held else None

    def _puts_in(self, current: _Run, given: _Given, session: SessionBase) -> None:
        import subprocess

        try:
            session.interject(given.text)
        except subprocess.CalledProcessError as refused:
            # A backend that refused it: codex drops a steer that named a turn already
            # over, and kimi answers one inside a 200. Either way it never went.
            said: object = refused.stderr
            if isinstance(said, bytes):
                said = said.decode(errors="replace")
            self._unreached(current, given, str(said or "the agent refused it"))
        except Exception as why:  # noqa: BLE001 -- whatever it was, the word never went
            self._unreached(current, given, str(why) or type(why).__name__)

    def _unreached(self, current: _Run, given: _Given, because: str) -> None:
        """Puts a word back at the head of the queue, the agent never having taken it."""
        with self._lock:
            if given in self._given:
                self._given.remove(given)
                self._queue.insert(
                    0, _Line(given.text, given.by, given.client, given.to)
                )
            self._record(
                {
                    "type": "refused",
                    "run": current.number,
                    "agent": given.agent,
                    "text": given.text,
                    "because": because,
                }
            )
            self._snap_waiting()
            self._spoke.notify_all()

    def _took(self, current: _Run, agent: AgentBase, key: str, text: str) -> bool:
        """Takes a word off what is given, the agent having said it has it. Under the lock."""
        given = next(
            (one for one in self._given if one.agent == agent.id and one.text == text),
            None,
        )
        if given is None:
            return False  # somebody else's word, or one already written down
        self._given.remove(given)
        self._record(
            {
                "type": "said",
                "run": current.number,
                "text": text,
                "key": key or given.key,
                "by": given.by,
                "client": given.client,
            }
        )
        self._snap_waiting()
        return True

    def _unholds(self, current: _Run, agent: AgentBase) -> None:
        """Says what an agent was holding when its turn ended. Under the lock."""
        held = [one for one in self._given if one.agent == agent.id]
        if not held:
            return
        self._given = [one for one in self._given if one.agent != agent.id]
        self._record(
            {
                "type": "unheld",
                "run": current.number,
                "agent": agent.id,
                "texts": [one.text for one in held],
            }
        )
        self._snap_waiting()

    def _drops(self, number: int, because: str) -> None:
        """Says what was still waiting when a run stopped or ended, and lets go of it."""
        if not (self._queue or self._given):
            return
        self._record(
            {
                "type": "dropped",
                "run": number,
                "given": [
                    {
                        "agent": one.agent,
                        "text": one.text,
                        "by": one.by,
                        "client": one.client,
                    }
                    for one in self._given
                ],
                "queued": [
                    {"text": one.text, "by": one.by, "client": one.client, "to": one.to}
                    for one in self._queue
                ],
                "because": because,
            }
        )
        self._queue.clear()
        self._given.clear()
        self._snap_waiting()

    # ---------------------------------------------------------------- questions

    def _live(self, number: int, role: str) -> bool:
        """Whether the run asking is still the one going, and somebody is there for it."""
        current = self._current
        return (
            current is not None
            and current.number == number
            and not self._closed
            and not self._nobody(role)
        )

    def _nobody(self, role: str) -> bool:
        """Whether nobody is there to answer as a role. Under the lock.

        A chat's person is nobody's outworlder, so away is never said of them: nobody is
        there for a chat only once it has folded away.
        """
        current = self._current
        if current is not None and current.run.kind == "chat":
            return self._folded
        return self._away_of.get(role, self._away_all)

    def _asks(self, number: int, question: Question) -> str | None:
        """Puts what a run asks whoever is outside it to every frontend, and waits.

        Called on a thread of the run's own, which waits here. A question with answers to
        choose from, or one asked while a turn is open, is answered by an `answer`; anything
        else is what to say next, answered by the oldest line waiting that its role may be
        answered with -- one said before it was asked included. The run going away, or the
        role going away, answers nobody, which the flow hears as whoever is outside being
        away.

        Args:
          number: Which run is asking, so that a run on its way out cannot take the answer
            meant for the one that replaced it.
          question: What it asks, and which `Outworlder` asks it: a question asked for a
            schema whole, with what is shown beside it, is always one to `answer`.

        Returns:
          The answer -- the JSON text of the value, for a question asked for a schema -- or
          None where nobody gave one.
        """
        schema = question.schema
        return self._waits(
            number,
            question.asker or "outworlder",
            question.text,
            () if schema is not None else question.options,
            "ask" if schema is not None else None,
            shaped=_Shaped(
                schema=schema,
                context=tuple(question.context),
                face=question.face,
                session=question.session,
                check=question.check,
            ),
        )

    def _shows(
        self,
        number: int,
        role: str,
        session: str,
        context: Sequence[Mapping[str, Any]],
    ) -> None:
        """Shows every frontend what a run pushes to whoever is outside it, asking nothing.

        Said only while that run is the one going and somebody is there for the role: a
        `show` never waits, and what nobody is there to see is not kept for later.

        Args:
          number: Which run shows it.
          role: The `Outworlder` role showing it.
          session: The outworlder session it is shown in, as `<role>/<n>`.
          context: What it shows, as context blocks' JSON forms.
        """
        with self._lock:
            if not self._live(number, role):
                return
            self._record(
                {
                    "type": "shown",
                    "run": number,
                    "role": role,
                    "session": session,
                    "context": [dict(one) for one in context],
                }
            )

    def _mounts(self, face: _Face) -> None:
        """Keeps a face a run mounts, for `face` to hand out by its hash, for the epic's life."""
        with self._lock:
            self._faces[face.hash] = (face.html, face.title)

    def _face(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del frontend
        hashed = str(said.get("hash") or "")
        with self._lock:
            found = self._faces.get(hashed)
        if found is None:
            return _no(f"no face {hashed}", 404)
        html, title = found
        return _ok(html=html, title=title)

    def _shaped(self, asked: _Question) -> dict[str, Any]:
        """What `asked` and `pending` say of a question beyond its text. Under the lock."""
        face = (
            {"hash": asked.face, "title": self._faces.get(asked.face, ("", ""))[1]}
            if asked.face
            else None
        )
        return {
            "schema": dict(asked.schema) if asked.schema is not None else None,
            "context": [dict(one) for one in asked.context],
            "face": face,
            "session": asked.session,
        }

    def _waits(
        self,
        number: int,
        role: str,
        text: str,
        options: Sequence[str],
        mode: str | None = None,
        *,
        shaped: _Shaped | None = None,
    ) -> str | None:
        """Puts one question to every frontend, and waits for its answer, as `_asks` says.

        Args:
          number: Which run or chat is asking.
          role: Whose question it is.
          text: The question.
          options: The answers to choose from.
          mode: `ask` or `listen`, where the asker says which -- a chat, whose next message
            is never a question and whose assistant's question always is -- or None for the
            mode its options and the turns open make it.
          shaped: The schema it is answered in, what is shown beside it, its face and its
            session, or None for a question of text alone.

        Returns:
          The answer, or None where nobody gave one.
        """
        shaped = shaped or _Shaped()
        with self._lock:
            current = self._current
            if current is None or not self._live(number, role):
                return None
            if mode == "listen" and current.ending:
                # An empty next message was said already, which this wait is answered by.
                return None
            working = list(current.working)
            if mode is None:
                mode = "ask" if options or working else "listen"
            # The conversation whose turn it stopped, where only one has a turn open to be it.
            key = current.numbered.get(working[0], "") if len(working) == 1 else ""
            asked = _Question(
                f"q{next(self._asking)}",
                number,
                role,
                text,
                tuple(options),
                mode,
                key,
                schema=shaped.schema,
                context=shaped.context,
                face=shaped.face,
                session=shaped.session,
                check=shaped.check,
            )
            self._questions.append(asked)
            self._record(
                {
                    "type": "asked",
                    "run": number,
                    "question": asked.id,
                    "role": role,
                    "text": asked.text,
                    "options": list(asked.options),
                    "mode": mode,
                    "key": key,
                    **self._shaped(asked),
                }
            )
            self._snap_pending()
            while True:
                if asked.state == "answered":
                    if mode == "listen":
                        # Whatever turn this answer starts is that line's turn, and takes
                        # nothing said to the run at large out of the queue on the way in:
                        # only a line said to its agent or its conversation by name.
                        self._handed = True
                    return asked.answer or None
                if asked.state == "withdrawn":
                    return None
                if not self._live(number, role):
                    self._withdraws(
                        asked,
                        "away" if self._nobody(role) else "over",
                    )
                    return None
                if (
                    mode == "listen"
                    and (line := self._line_for(current, role)) is not None
                ):
                    self._queue.remove(line)
                    self._answers(asked, line.text, line.by, line.client)
                    self._snap_waiting()
                    continue
                # Re-asked every tick as well as on every word, so that a run that has
                # gone is noticed however it came about.
                self._spoke.wait(_TICK)

    def _line_for(self, current: _Run, role: str) -> _Line | None:
        """The oldest line waiting that answers what a role asks, where one does.

        One said to the run at large or to the role does. And in a chat, whose every question
        between turns is what to say next and whose every line is said to it, so does any
        line it was said: a native one held for this turn, and one that found no turn open to
        go into. Under the lock.
        """
        chat = current.run.kind == "chat"
        return next(
            (
                one
                for one in self._queue
                if (chat or one.to in ("", f"{_OUTWORLDER}{role}"))
                and self._may(one.client, role)
            ),
            None,
        )

    def _answers(self, asked: _Question, text: str, by: str, client: str) -> None:
        """Takes an answer for a question. Under the lock."""
        asked.state, asked.answer = "answered", text
        if asked in self._questions:
            self._questions.remove(asked)
        self._answered[asked.id] = by
        self._record(
            {
                "type": "answered",
                "run": asked.run,
                "question": asked.id,
                "role": asked.role,
                "by": by,
                "client": client,
                "text": _unsecret(text, asked.schema),
            }
        )
        self._snap_pending()
        self._spoke.notify_all()

    def _withdraws(self, asked: _Question, why: str) -> None:
        """Takes a question back, nobody being left to answer it. Under the lock."""
        asked.state = "withdrawn"
        if asked in self._questions:
            self._questions.remove(asked)
        self._record(
            {"type": "withdrawn", "run": asked.run, "question": asked.id, "why": why}
        )
        self._snap_pending()
        self._spoke.notify_all()

    def _releases(self, number: int) -> None:
        """Takes back every question one run is waiting on, the run being over."""
        for asked in [one for one in self._questions if one.run == number]:
            self._withdraws(asked, "over")

    def _answer(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        if self._slot.startswith("chat:"):
            return _no(_TO_CHAT)
        question = str(said.get("question") or "")
        text = said.get("text")
        sent = said.get("value")
        # A value of null is one not sent.
        valued = sent is not None
        if valued and text is not None:
            return _no("an answer is text or a value, not both")
        if not valued and (not isinstance(text, str) or not text):
            # Nothing is what nobody being there answers, and the flow hears it as that.
            return _no("an answer says something")
        with self._lock:
            asked = self._answerable(frontend, question)
        if isinstance(asked, dict):
            return asked
        if asked.schema is None and not valued:
            answer = _chosen(asked.options, cast("str", text))
            value: Any = answer
        elif asked.schema is None:
            value = sent
            if not isinstance(value, str):
                return _misfit(({"path": [], "message": "text is expected"},))
            if not value:
                return _no("an answer says something")
            answer = value
        else:
            value = sent if valued else _parsed(cast("str", text))
            if value is _UNPARSED:
                return _misfit(({"path": [], "message": "the answer is not JSON"},))
            answer = json.dumps(value, ensure_ascii=False)
        # Off the lock: the flow's own check, which nothing else here waits on.
        misfits = _misfits(asked, value)
        if misfits:
            return _misfit(misfits)
        with self._lock:
            # Answered, withdrawn or claimed by somebody else while it was checked.
            again = self._answerable(frontend, question)
            if isinstance(again, dict):
                return again
            self._answers(asked, answer, frontend.name, frontend.client)
        return _ok()

    def _answerable(
        self, frontend: _Frontend, question: str
    ) -> _Question | dict[str, Any]:
        """The question waiting that a frontend may answer, or why not. Under the lock."""
        asked = next((one for one in self._questions if one.id == question), None)
        if asked is None:
            if question in self._answered:
                return _no(f"already answered by {self._answered[question]}")
            return _no(f"no question {question} is waiting")
        owner = self._claims.get(asked.role)
        if owner not in (None, frontend.client):
            return _no(f"{asked.role} is {self._name_of(owner or '')}'s")
        return asked

    # ----------------------------------------------------------- claims and away

    def _claim(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        role = str(said.get("role") or "")
        if not role:
            return _no("a role to claim is named")
        with self._lock:
            owner = self._claims.get(role)
            if owner not in (None, frontend.client) and not said.get("take"):
                return _no(f"{role} is {self._name_of(owner or '')}'s")
            self._claims[role] = frontend.client
            self._snap_claims()
            self._spoke.notify_all()
        return _ok()

    def _release(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        role = str(said.get("role") or "")
        with self._lock:
            if self._claims.get(role) != frontend.client:
                return _no(f"{role or 'that'} is not yours to release")
            del self._claims[role]
            self._snap_claims()
            self._spoke.notify_all()
        return _ok()

    def _afk(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        on = said.get("on")
        if not isinstance(on, bool):
            return _no("afk is on or off")
        role = str(said.get("role") or "")
        with self._lock:
            if role:
                if not self._may(frontend.client, role):
                    return _no(f"{role} is {self._name_of(self._claims[role])}'s")
                self._away_of[role] = on
            elif not self._claims:
                # Nobody holds any role, so it is the one switch it always was.
                self._away_all = on
                self._away_of.clear()
            else:
                # Every role this frontend may speak for, which is every role but the ones
                # somebody else holds -- and those stay exactly as they were.
                for claimed, owner in self._claims.items():
                    if owner != frontend.client:
                        self._away_of[claimed] = self._away_of.get(
                            claimed, self._away_all
                        )
                self._away_all = on
                for held in [
                    one for one in self._away_of if self._may(frontend.client, one)
                ]:
                    del self._away_of[held]
            self._goes_away()
        return _ok()

    def _goes_away(self) -> None:
        """Says who is away, and withdraws every question of a role that is. Under the lock.

        Withdrawn now, not when the asking thread next looks: away set and cleared again
        before it looks would leave its question waiting for nobody.
        """
        self._snap("away", all=self._away_all, of=dict(self._away_of))
        for asked in [one for one in self._questions if self._nobody(one.role)]:
            self._withdraws(asked, "away")
        self._spoke.notify_all()

    # --------------------------------------------------------------------- board

    def _snap_board(self, board: Board) -> None:
        self._snap(
            "board",
            items=[
                {
                    "key": one.key,
                    "value": one.value,
                    "about": one.about,
                    "whose": one.whose,
                    "by": one.by,
                    "at": one.at,
                }
                for one in board.items()
            ],
        )

    def _boarded(self, current: _Run, board: Board) -> None:
        with self._lock:
            if current is self._last:
                self._snap_board(board)

    def _board(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del frontend
        from hmz.coganchor.agents.board import USER

        key = str(said.get("key") or "")
        value = str(said.get("value") or "")
        with self._lock:
            shown = self._last
            board = shown.board if shown is not None else None
        if board is None:
            return _no("this run has no board")
        try:
            if value:
                board.put(key, value, by=USER)
            elif not board.drop(key, by=USER):
                return _no(f"{key} is not on the board")
        except (PermissionError, ValueError) as why:
            return _no(str(why))
        return _ok()

    # -------------------------------------------------------------------- asides

    def _aside(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        side = said.get("side")
        if side:
            return self._turns(frontend, str(side), str(said.get("prompt") or ""))
        key = str(said.get("key") or "")
        runs = str(said.get("runs") or "")
        with self._lock:
            shown = self._last
            found = shown.known.get(key) if shown is not None and key else None
        if key and found is None:
            return _no(f"{key} has no conversation to ask")
        if found is not None:
            agent, session = found
            opened, forked = _side_of(agent, session, key, fork=bool(said.get("fork")))
        elif runs:
            # A session of an earlier run, carried on from where that run kept it where it
            # says where, and otherwise a new session of its agent.
            made = _made(runs)
            if made is None:
                return _no(f"{runs} is not an agent that can be made here")
            opened, forked = _recalled(
                made,
                str(said.get("recall") or ""),
                str(said.get("kept") or ""),
                str(said.get("cwd") or self._hmz.workspace),
                fork=bool(said.get("fork")),
            )
        else:
            return _no("an aside is about a conversation, or asks an agent")
        with self._lock:
            if self._frontends.get(frontend.client) is not frontend:
                _closed_all([opened])
                return _no("this frontend has gone")
            side = f"s{next(self._sides)}"
            self._asides[side] = _Aside(side, frontend.client, opened)
        return _ok(side=side, forked=forked)

    def _turns(self, frontend: _Frontend, side: str, prompt: str) -> dict[str, Any]:
        with self._lock:
            aside = self._asides.get(side)
            if aside is None or aside.client != frontend.client:
                return _no(f"no aside {side} is open")
            if aside.busy:
                return _no("the aside is still answering the last question")
            aside.busy = True
        try:
            answer = str(aside.session(prompt) or "").strip()
        finally:
            with self._lock:
                aside.busy = False
        return _ok(answer=answer)

    def _unaside(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        side = str(said.get("side") or "")
        with self._lock:
            aside = self._asides.get(side)
            if aside is None or aside.client != frontend.client:
                return _no(f"no aside {side} is open")
            del self._asides[side]
        _closed(aside.session)
        return _ok()


def assistant(agent: str) -> Runs:
    """A chat's agent, as `-a` spells one after `<role>=`, read as a chat takes it.

    Args:
      agent: The agent.

    Returns:
      It, as settings keep an agent.

    Raises:
      ValueError: Saying why, for one that is not an agent (Section 8.3.7 of core.md).
    """
    from hmz.runtime.flowing.specs import parse_agents
    from hmz.runtime.kept import read_back

    # What -a refuses, in its words; then what a setting could not be written as.
    parse_agents([f"assistant={agent}"])
    runs = read_back(agent)
    if runs is None:
        raise ValueError(f"{agent} is not an agent as -a spells one.")
    return runs


def _her(said: Mapping[str, Any]) -> Role:
    """Ai-chan's role, for the conversation whose reach and scratch directory `said` holds.

    Raises:
      ValueError: For a reach that is not one.
      OSError: Where no scoped link is named.
      HarnessSandboxed: Where her confinement cannot be held here.
    """
    from hmz.runtime.doing.aichan import Reach, role

    return role(Reach.model_validate(said["ai"]), Path(str(said.get("scratch") or "")))


def _unpermitted(permission: object) -> str:
    """Why a chat cannot be held to `permission`, or "" where it is a preset or None."""
    from hmz.runtime.chatting import preset

    try:
        if permission is not None:
            preset(permission)
    except ValueError as why:
        return str(why)
    return ""


def chat_set_refused(said: Mapping[str, Any]) -> str:
    """Why `chat.set` cannot take what it was given, or "" where it can.

    Args:
      said: `prefer`, `permission` or both, as `chat.set` takes them (Section 4.25.4 of
        daemon.md).
    """
    prefer, permission = said.get("prefer"), said.get("permission")
    if prefer is None and permission is None:
        return "chat.set takes prefer or permission"
    if prefer not in (None, "native", "flow"):
        return "prefer is native or flow"
    return _unpermitted(permission)


def chat_checked(hmz: Hmz, said: Mapping[str, Any]) -> dict[str, Any]:
    """What a chat is to be started with, checked before anything is started for it.

    What `chat.start` refuses before a host is asked (Section 4.25.1.6 of daemon.md), the same
    whoever asks: no task for a chat that is not carried on, no agent and no chat carried on
    to take one from, an agent that is
    not one, a preference that is neither, a permission that is no preset, a chat to carry
    on that is no chat of this workspace, and a worktree asked for a chat carried on.

    Args:
      hmz: The workspace.
      said: `agent`, `task`, `resume`, `prefer`, `permission` and `worktree`, as `chat.start`
        takes them.

    Returns:
      `ok` with `agent` (the carried-on chat's own where none was named), `runs` (it, as
      settings keep it), `task`, `resume` (the chat's directory, or None), `prefer`,
      `permission` and `worktree`; or `ok` false with `why` and the `code` to refuse it with.
    """
    task, prefer = said.get("task"), said.get("prefer")
    # An Ai-chan conversation started with nothing said waits, between turns, for what is;
    # and so does a chat carried on with nothing said, whose workspace is reached meanwhile.
    ai = said.get("ai") is not None
    if not isinstance(task, str) or not (task or ai or said.get("resume")):
        return _no("a chat starts with something said", 400)
    if prefer not in (None, "native", "flow"):
        return _no("prefer is native or flow", 400)
    permission = said.get("permission")
    if unpermitted := _unpermitted(permission):
        return _no(unpermitted, 400)
    agent = str(said.get("agent") or "")
    resume = str(said.get("resume") or "")
    carried: Path | None = None
    if resume:
        # Hers by its directory, which the daemon keeps for her; any other by its name.
        carried = Path(resume) if ai else hmz.epics.chat(resume)
        if carried is None:
            return _no(f"{resume} is not a chat of {hmz.workspace}.", 404)
        if said.get("worktree") is True:
            return _no("a chat carried on works where it worked", 400)
        if not agent or permission is None:
            # What the chat had, where it is carried on with none of its own named.
            ran = hmz.epics.read(carried)
            if not agent:
                agent = ran.agents[0].spec if ran is not None and ran.agents else ""
            if (
                permission is None
                and ran is not None
                and not _unpermitted(ran.permission)
            ):
                permission = ran.permission or None
    if not agent:
        return _no("an agent for the chat is named", 400)
    try:
        from hmz.coganchor import nous
        from hmz.runtime.flowing.specs import parse_agents

        (named,) = parse_agents([f"assistant={agent}"])
        # A nous by name is no agent a setting keeps (Section 3.4.1.6 of core.md): hers is
        # not kept, and a chat's is kept as the concrete nous it starts at.
        runs = None if ai else assistant(nous.entry(agent) if named.nous else agent)
    except ValueError as why:
        return _no(str(why), 400)
    return _ok(
        agent=agent,
        runs=runs,
        task=task,
        resume=str(carried) if carried is not None else None,
        prefer=prefer,
        permission=permission,
        worktree=said.get("worktree") is True,
    )


def _natives(run: Chatting) -> list[NativeCommand]:
    """A chat's native catalogue as its conversation stands, or none where it cannot say."""
    try:
        return list(run.chat.natives())
    except Exception:  # noqa: BLE001 -- a catalogue nobody could read holds nothing
        return []


#: What a text that is not JSON parses to, there being no JSON value it could be.
_UNPARSED = object()


def _parsed(typed: str) -> Any:
    """The JSON value a text answering a schema question writes, or `_UNPARSED`."""
    try:
        return json.loads(typed)
    except ValueError:
        return _UNPARSED


def _misfits(asked: _Question, value: Any) -> tuple[Mapping[str, Any], ...]:
    """Every way a value does not fit a question, by its own check: a check that fails, one."""
    if asked.check is None:
        return ()
    try:
        return tuple(asked.check(value))
    except Exception as why:  # noqa: BLE001 -- a check that cannot read a value is not fitted
        return ({"path": [], "message": str(why) or type(why).__name__},)


def _misfit(errors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The refusal of an answer that does not fit its question, saying every way it does not."""
    said = [
        {"path": list(one.get("path") or ()), "message": str(one.get("message") or "")}
        for one in errors
    ]
    return _no(f"the answer does not fit: {said[0]['message']}", 400, {"errors": said})


def _chosen(options: tuple[str, ...], typed: str) -> str:
    """What a line typed at a question answers: the answer it numbers, or the line itself."""
    said = typed.strip()
    if said.isdigit() and said not in options:
        at = int(said)
        if 1 <= at <= len(options):
            return options[at - 1]
    return typed


def _made(runs: str) -> AgentBase | None:
    """An agent as `-a` spells one after its role, or None for one that cannot be made."""
    from hmz.coganchor.agents import driver
    from hmz.coganchor.agents.base import identifying
    from hmz.runtime.flowing.specs import parse_agents

    try:
        spec = parse_agents([f"btw={runs}"])[0]
        kind, made = driver(spec.cli)
        return kind(
            made(
                model=spec.model,
                effort=spec.effort,
                provider=spec.provider,
                nous=spec.nous,
                **identifying(made, spec.cli),
            )
        )
    except Exception:  # noqa: BLE001 -- a spec nothing is made from answers as such
        return None


def _read_only(source: AgentBase, name: str) -> AgentBase:
    """A read-only agent like another, invisible to the run it was taken from.

    Held to a fence that writes nothing (:meth:`~hmz.coganchor.fence.Fence.reading`): the
    read-only twin of the agent's own fence, or one that reads the whole machine for an agent
    that has none -- one made by hand, or of a run nothing fenced. Its harness is told so as
    it is told any fence that writes nothing, and the fence holds whatever it is told; so a
    harness that cannot be told to write nothing answers a side question as well as any.

    Args:
      source: The agent.
      name: What the copy is called.

    Raises:
      Unfenced: If the fence cannot be held on this machine, saying so -- rather than a side
        question answered by an agent that could write.
    """
    from hmz.coganchor.fence import READ, Fence
    from hmz.runtime.flowing.harnessing import ASKING_FEATURE

    fence = source.config.fence
    reading = (
        fence.reading()
        if fence is not None
        else Fence.of(rules=[("/", READ)], online=True, workdir=os.sep, home="")
    )
    settings: dict[str, object] = {"fence": reading, "goals": False}
    # Claude's allow-list can approve a write in a normal permission mode, and Cursor's MCP
    # approval would reach every server this workspace names on the flow's say-so.
    if hasattr(source.config, "allowed_tools"):
        settings["allowed_tools"] = ()
    # Claude's `asks` would start the copy at `manual`, putting every request to approval, and
    # Kimi's at `yolo` -- a source's hook hung on PERMISSION_REQUEST is not the side
    # conversation's to wait on.
    if hasattr(source.config, "asks"):
        settings["asks"] = False
    if hasattr(source.config, "approve_mcps"):
        settings["approve_mcps"] = False
    # Nothing is let out of Codex's read-only sandbox.
    if hasattr(source.config, "unsandboxed"):
        settings["unsandboxed"] = ()
    # Codex's `approvals` would open the copy's thread at `untrusted` over the `never` its
    # fence is told with, and its asking feature would let it ask a user nobody plays: both
    # are there for hooks hung on the source, and none is hung on the copy.
    if hasattr(source.config, "approvals"):
        settings["approvals"] = ""
    features = cast(
        "tuple[tuple[str, Any], ...] | None", getattr(source.config, "features", None)
    )
    if features is not None:
        settings["features"] = tuple(
            one for one in features if one[0] != ASKING_FEATURE
        )
    clone = source.clone(
        config=dataclasses.replace(source.config, **settings), name=name, skills=()
    )
    # Watched by nothing that shows it, so a command-backed backend does not echo the side
    # answer onto the stdout of whatever is holding the run.
    clone.watch(lambda _agent, _session, _event: None)
    return clone


def _recalled(
    agent: AgentBase, ident: str, kept: str, cwd: str, *, fork: bool
) -> tuple[SessionBase, bool]:
    """A side conversation about a session an earlier run kept: a fork of it where it can be.

    The conversation is brought in where nothing else is kept -- a directory of the side
    conversation's own, taken away as it is closed -- so that neither the earlier run nor the
    CLI's own home is written into. Where it cannot be forked, or was not kept, a fresh copy of
    its agent is opened instead, to be told what it is about.

    Args:
      agent: The agent the session was of.
      ident: What its CLI called the conversation.
      kept: Where the earlier run kept it, laid out as the CLI lays out its home.
      cwd: The directory it worked in.
      fork: Whether a fork carrying its history is asked for.

    Returns:
      The conversation, and whether it is a fork carrying the history.
    """
    from hmz import machine

    scratch = Path(tempfile.mkdtemp(prefix="aside-", dir=machine()))
    agent.keeps = scratch
    held: SessionBase | None = None
    try:
        held = agent.recall(ident, kept, cwd) if fork and kept else None
    except (NotImplementedError, RuntimeError, OSError):
        held = None
    if held is not None:
        opened, forked = _side_of(agent, held, f"recall-{ident[:8]}", fork=True)
        with contextlib.suppress(Exception):
            held.close()
    else:
        opened, forked = _read_only(agent, f"btw-{ident[:8]}").new(cwd), False
    _SCRATCH[id(opened)] = scratch
    return opened, forked


def _side_of(
    agent: AgentBase, session: SessionBase, key: str, *, fork: bool
) -> tuple[SessionBase, bool]:
    """A side conversation about one of the run's: a fork of it where asked and possible.

    Returns:
      The conversation, and whether it is a fork carrying the history -- rather than a
      fresh one of a copy of its agent, which is to be told what it is about.
    """
    if fork and session.forks:
        forked: SessionBase | None = None
        try:
            forked = session.fork(into=_read_only(agent, f"btw-{key}"))
            forked.loads(())
            forked.offers(None)
        except Exception:  # noqa: BLE001 -- the copy below is what is left to try
            if forked is not None:
                _closed_all([forked])
        else:
            return forked, True
    try:
        cwd: str | None = session.cwd
    except (OSError, RuntimeError, ValueError):
        cwd = None
    return _read_only(agent, f"btw-{key}").new(cwd), False
