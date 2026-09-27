"""One workspace's runs, shared by every frontend attached to them.

A run used to have one person outside it: whoever was at the one interface that started it.
The queue of lines typed at it, the questions it stopped on, who was away, which conversation
was `builder/2` -- all of it lived in that interface, because that interface was the only one.
A day's work watched by two people, or by a person and a bot, is two frontends on one run, and
each of those things has to be answered once rather than once per frontend or the two
disagree about what the run is doing.

So they are answered here, where the run is. A frontend is anything that attaches: an
interface, `hmz attach`, a program written against the SDK. It is handed everything as
messages -- what the run's agents said, what was asked and answered, who holds which role --
and asks for everything as requests, one reply apiece. Nothing here knows whether a frontend
is in this process or on the other end of a socket: the daemon carries the same messages both
ways and hands a frontend the same :class:`hmz.daemon.link.Link` either way.

What is held for them:

- *claims*: a role an `Outworlder` fills, held by one frontend at a time and given up when it
  goes. Only its claimant answers for it; a role nobody claims is anybody's, first answer wins.
- *away*: per role and not per frontend, since it is a fact about the run -- whether a question
  of that role is waited on -- and it outlives the frontend that said it.
- *lines*: what is said to the run's agents, queued per target and handed over one at a time.
- *keys*: which conversation is `<role>/<n>`, numbered once so every frontend names it alike.
- *asides*: the side conversations `/btw` opens, read-only and invisible to the run.
- *history*: every record of the run, in order, so a frontend arriving late reads it all.

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
import threading
import time
import weakref
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from hmz.coganchor.agents import AgentBase, Board, Event, Question, SessionBase
    from hmz.runtime.doing.core import Hmz
    from hmz.runtime.doing.running import Run

__all__ = ["PROTOCOL", "Host", "record"]

#: Which version of the messages this speaks, said to every frontend as it arrives.
PROTOCOL = 1

#: How long one text in a message may be before the rest of it is counted instead. A turn's
#: answer is kilobytes; a tool that printed a file is the case this is for, and a frame of the
#: socket carrying it has a ceiling of its own.
_LONGEST = 256 * 1024

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
      key: The transcript it goes on: the conversation's `<role>/<n>`, or where the agent's
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


def _clipped(said: Any) -> Any:
    """What a message says, with any text too long to carry cut and the rest counted."""
    if isinstance(said, str):
        if len(said) <= _LONGEST:
            return said
        return f"{said[:_LONGEST]}… ({len(said) - _LONGEST} more characters)"
    if isinstance(said, dict):
        return {key: _clipped(value) for key, value in said.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(said, list):
        return [_clipped(one) for one in said]  # pyright: ignore[reportUnknownVariableType]
    return said


def _sized(message: dict[str, Any]) -> int:
    """How many bytes a message comes to written, which is what every ceiling is kept in."""
    return len(json.dumps(message, default=str, ensure_ascii=False).encode())


def _ok(**said: Any) -> dict[str, Any]:
    return {"ok": True, **said}


def _no(why: str) -> dict[str, Any]:
    return {"ok": False, "why": why}


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
    """A pydantic model as JSON-native values, `Infinity` spelled as it reads back."""
    return json.loads(model.model_dump_json())


def _spoken(given: Mapping[str, Any]) -> dict[str, str]:
    """What each role was given, as the words `-a` or `-e` would spell it."""
    return {
        role: said if isinstance(said, str) else str(getattr(said, "spec", said))
        for role, said in given.items()
    }


def _closed_all(sessions: list[SessionBase]) -> None:
    """Closes side conversations, off whatever thread let go of them."""

    def closes() -> None:
        for one in sessions:
            with contextlib.suppress(Exception):
                one.close()

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
    state: str = "pending"
    answer: str = ""


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
    run: Run
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


class Host:
    """One workspace's runs, shared by every frontend attached to them."""

    def __init__(self, hmz: Hmz) -> None:
        """Holds the workspace and no run, with nobody attached.

        Args:
          hmz: The workspace, which runs are started in.
        """
        self._hmz = hmz
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
        self._runs = 0
        self._starting = False
        self._questions: list[_Question] = []
        self._asking = itertools.count(1)
        self._answered: dict[str, str] = {}
        self._queue: list[_Line] = []
        self._given: list[_Given] = []
        self._handed = False
        self._asides: dict[str, _Aside] = {}
        self._sides = itertools.count(1)
        self._keeps = False
        self._closed = False
        #: The thread each run started here is driven on, for closing to wait for.
        self._driving: list[threading.Thread] = []
        self._ticking: threading.Thread | None = None
        self._spent_at = 0.0
        self._requests: dict[
            str, Callable[[_Frontend, dict[str, Any]], dict[str, Any]]
        ] = {
            "start": self._start,
            "say": self._say,
            "answer": self._answer,
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
        }
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

    # ----------------------------------------------------------------- frontends

    def attach(
        self,
        name: str,
        kind: str,
        heard: Callable[[dict[str, Any]], None],
        *,
        replay: bool = True,
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
            welcome = {
                "type": "welcome",
                "client": client,
                "name": named,
                "kind": kind,
                "workspace": str(self._hmz.workspace),
                "pid": os.getpid(),
                "protocol": PROTOCOL,
            }
            self._post(frontend, welcome, _sized(welcome))
            if replay:
                for message, size in self._history:
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

    def status(self) -> dict[str, Any]:
        """What there is to say about the runs here, for somebody asking from outside them.

        Returns:
          How many frontends are attached and who, the state and number of the run, the
          flow, what it may spend and has spent -- both None with nothing running -- and the
          flows running, as refs and as calls.
        """
        with self._lock:
            running = self._current
            shown = running or self._stopping or self._last
            clients = self._clients_of()
            state = self._state()
        calls = self._calls(now=time.monotonic())
        return {
            "attached": len(clients),
            "clients": clients,
            "state": state,
            "run": shown.number if shown is not None else 0,
            "flow": shown.run.flow if shown is not None else "",
            "budget": _json(running.run.budget) if running is not None else None,
            "usage": _json(running.run.usage) if running is not None else None,
            "flows": [one["ref"] for one in calls],
            "calls": calls,
        }

    def close(self) -> None:
        """Closes every run here and lets every frontend go, telling each why.

        And waits a while for those runs to let go of what they made, however many times it is
        called: whoever closes a host may be about to end the process holding it, and what a
        run had not taken down by then -- a container -- would outlive it.
        """
        self._close()
        with self._lock:
            driving = list(self._driving)
        until = time.monotonic() + _LETTING_GO
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
        written: dict[str, Any] = _clipped({"type": kind, "seq": self._seq, **message})
        size = _sized(written)
        self._history.append((written, size))
        self._kept += size
        while self._kept > _KEPT and len(self._history) > 1:
            _, gone = self._history.popleft()
            self._kept -= gone
            self._elided += 1
        self._broadcast(written, size)

    def _snap(self, kind: str, **fields: Any) -> None:
        """Says how one thing stands now, where that has changed since it was last said."""
        message: dict[str, Any] = _clipped({"type": kind, **fields})
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
                    "owner": self._claims.get(one.role),
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
        )

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
        with self._lock:
            if self._closed:
                return _no("this host has closed")
            if self._current is not None:
                return _no("a flow is already running")
            if self._starting:
                return _no("a flow is already starting")
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
                resume=resume,
                # Whoever is outside the run is every frontend here: asked on a thread of
                # the run's own, and away while `/afk` says so.
                outworlder=open_outworlder(
                    ask=functools.partial(self._asks, number), away=self.away_for
                ),
            )
            declared = run.declaration
            started: dict[str, Any] = {
                "run": number,
                "flow": flow,
                "ref": run.ref,
                "task": task,
                "by": frontend.name,
                "client": frontend.client,
                "roles": [one.name for one in declared.agents if not one.auto],
                "outworlders": [one.name for one in declared.agents if one.auto],
                "agents": _spoken(agents) if isinstance(agents, dict) else {},
                "envs": _spoken(envs) if isinstance(envs, dict) else {},
                "params": dict(params) if isinstance(params, dict) else {},  # pyright: ignore[reportUnknownArgumentType]
                "budget": _json(run.budget),
                "resume": str(resume) if resume else "",
                "began": time.monotonic(),
                "at": time.time(),
            }
        except Exception as why:  # noqa: BLE001 -- a flow that will not start is a line to fix
            with self._lock:
                self._starting = False
            return _no(str(why) or type(why).__name__)
        current = _Run(number, run, started)
        with self._lock:
            self._starting = False
            if self._closed:
                # Closed while the flow was loading: nothing of it is started.
                return _no("this host has closed")
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
        run.watch(functools.partial(self._heard, current))
        run.opened(functools.partial(self._opened, current))
        driving = threading.Thread(
            target=self._drives, args=(current,), daemon=True, name="humanize-run"
        )
        with self._lock:
            self._driving = [one for one in self._driving if one.is_alive()]
            self._driving.append(driving)
        driving.start()
        return _ok(run=number)

    def _drives(self, current: _Run) -> None:
        """Runs one flow to its end, and says how it ended."""
        import asyncio
        import traceback

        from hmz.coganchor.agents import Stopped
        from hmz.flows import BudgetExceeded, FlowException
        from hmz.runtime import telemetry
        from hmz.runtime.runner import Refused

        how, why = "done", ""
        try:
            current.run.run()
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
            telemetry.crash(crashed, doing="a flow")
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
                # arrive is the one it ended for.
                if not self._frontends and not current.stopped_by:
                    self._keeps = True
            self._record(
                {
                    "type": "ended",
                    "run": current.number,
                    "how": how,
                    "why": why,
                    "mono": time.monotonic(),
                }
            )
            self._snap_run()
            self._snap_sessions(self._current or self._stopping or current)
            if self._last is current and spent is not None:
                self._snap("usage", **spent)
            self._spoke.notify_all()

    def _stop(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del said
        with self._lock:
            current = self._current
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
        return _ok(closed=len(closing))

    def _quit(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del frontend, said
        self.close()
        return _ok()

    def _detach(self, frontend: _Frontend, said: dict[str, Any]) -> dict[str, Any]:
        del said
        self.detach(frontend.client)
        return _ok()

    # ---------------------------------------------------------------- what opened

    def _opened(
        self, current: _Run, role: str, agent: AgentBase, session: SessionBase
    ) -> None:
        """Takes one session the run opened as one of its own, before its first turn."""
        from hmz.coganchor.agents import HumanAgent

        person = isinstance(agent, HumanAgent)
        board: Board | None = None
        with self._lock:
            # Numbered now, in the order the run opens them, rather than as each first
            # speaks: `builder/2` is the second conversation a builder opened.
            key = self._key_of(current, agent, session)
            current.agents.append(agent)
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
                    "kept": "" if person else str(agent.kept()),
                    "mono": time.monotonic(),
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

        What no one conversation said goes on the one working, or the newest, and on the role
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
        nothing meant for the run that replaced it -- and none where the person has just
        answered what to say next, which this turn is already about.
        """
        with self._lock:
            if current is not self._current:
                return []
            if self._handed:
                self._handed = False
                return []
            key = current.numbered.get(session, agent.id)
            line = next(
                (one for one in self._queue if one.to in ("", agent.id, key)), None
            )
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

        A conversation's own view is that conversation; a role's is its newest working one;
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
        from hmz.runtime import telemetry

        # How long the refusal was and nothing of what it said: it is a backend's stderr.
        telemetry.snag("line-refused", said=len(because))
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
        from hmz.runtime import telemetry

        # Counted rather than read: what they said is theirs.
        telemetry.snag("lines-never-sent", how_many=len(self._queue) + len(self._given))
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
            and not self._away_of.get(role, self._away_all)
        )

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
          question: What it asks, and which `Outworlder` asks it.

        Returns:
          The answer, or None where nobody gave one.
        """
        role = question.asker or "outworlder"
        with self._lock:
            current = self._current
            if current is None or not self._live(number, role):
                return None
            mode = "ask" if question.options or len(current.working) else "listen"
            asked = _Question(
                f"q{next(self._asking)}",
                number,
                role,
                question.text,
                tuple(question.options),
                mode,
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
                }
            )
            self._snap_pending()
            while True:
                if asked.state == "answered":
                    if mode == "listen":
                        # Whatever turn this answer starts is that line's turn, and takes
                        # nothing else out of the queue on the way in.
                        self._handed = True
                    return asked.answer or None
                if asked.state == "withdrawn":
                    return None
                if not self._live(number, role):
                    self._withdraws(
                        asked,
                        "away" if self._away_of.get(role, self._away_all) else "over",
                    )
                    return None
                if mode == "listen" and (line := self._line_for(role)) is not None:
                    self._queue.remove(line)
                    self._answers(asked, line.text, line.by, line.client)
                    self._snap_waiting()
                    continue
                # Re-asked every tick as well as on every word, so that `/afk` and a run
                # that has gone are noticed however they came about.
                self._spoke.wait(_TICK)

    def _line_for(self, role: str) -> _Line | None:
        """The oldest line waiting that answers what a role asks, where one does."""
        wanted = ("", f"{_OUTWORLDER}{role}")
        return next(
            (
                one
                for one in self._queue
                if one.to in wanted and self._may(one.client, role)
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
                "text": text,
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
        question = str(said.get("question") or "")
        text = said.get("text")
        if not isinstance(text, str) or not text:
            # Nothing is what nobody being there answers, and the flow hears it as that.
            return _no("an answer says something")
        with self._lock:
            asked = next((one for one in self._questions if one.id == question), None)
            if asked is None:
                if question in self._answered:
                    return _no(f"already answered by {self._answered[question]}")
                return _no(f"no question {question} is waiting")
            owner = self._claims.get(asked.role)
            if owner not in (None, frontend.client):
                return _no(f"{asked.role} is {self._name_of(owner or '')}'s")
            self._answers(
                asked, _chosen(asked.options, text), frontend.name, frontend.client
            )
        return _ok()

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
            self._snap("away", all=self._away_all, of=dict(self._away_of))
            self._spoke.notify_all()
        return _ok()

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
            made = _made(runs)
            if made is None:
                return _no(f"{runs} is not an agent that can be made here")
            opened, forked = (
                _read_only(made, "btw").new(str(self._hmz.workspace)),
                False,
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
        with contextlib.suppress(Exception):
            aside.session.close()
        return _ok()


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
                **identifying(made, spec.cli),
            )
        )
    except Exception:  # noqa: BLE001 -- a spec nothing is made from answers as such
        return None


def _read_only(source: AgentBase, name: str) -> AgentBase:
    """A read-only, skill-free agent like another, invisible to the run it was taken from."""
    # The read-only rung is what a flow's NONE maps to; a backend that cannot express it
    # raises here rather than running a side question with write permissions.
    settings: dict[str, object] = {"permission": "read-only", "goals": False}
    # Claude's allow-list can approve a write in a normal permission mode, and Cursor's MCP
    # approval would reach every server this workspace names on the flow's say-so.
    if hasattr(source.config, "allowed_tools"):
        settings["allowed_tools"] = ()
    if hasattr(source.config, "approve_mcps"):
        settings["approve_mcps"] = False
    clone = source.clone(
        config=dataclasses.replace(source.config, **settings),
        name=name,
        skills=(),
    )
    # Watched by nothing that shows it, so a command-backed backend does not echo the side
    # answer onto the stdout of whatever is holding the run.
    clone.watch(lambda _agent, _session, _event: None)
    return clone


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
