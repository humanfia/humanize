"""One frontend's end of a workspace's runs: requests out, and messages about the runs in.

A frontend -- an interface, `hmz attach`, a program -- reaches the runs of a workspace one of
two ways: over the socket of the host holding them where a terminal closing cannot end them,
or in its own process, holding them itself. Both are this, so that a frontend is written once
and is told which of the two it has been handed where it asks for one.

What it is told arrives in order, on a thread that is not the caller's: handed to a listener
once one is set, and read by iterating the link until then. What it asks is answered on the
thread that asked, one request one reply, with a refusal raised as the runtime's own
:class:`hmz.runtime.Refused` and in the same words whichever way it was reached.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import queue
import socket
import threading
from typing import TYPE_CHECKING, Any, Self

from hmz.daemon import where
from hmz.daemon.proto import GONE, MESSAGE, Frames, asked, frame

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterator, Mapping
    from pathlib import Path
    from types import TracebackType

    from hmz.runtime import Host

__all__ = ["Link", "linked", "reached"]

#: How long a host is given to say hello back.
_PATIENCE = 10.0

#: How much is read off the socket at a time.
_READ = 1 << 16


def _plain(model: Any) -> Any:
    """A pydantic model or a mapping as JSON-native values, and None as itself."""
    if model is None:
        return None
    if hasattr(model, "model_dump_json"):
        return json.loads(model.model_dump_json())
    return dict(model)


class Link:
    """One frontend attached to a workspace's runs; a context manager.

    Attributes:
      client: Its client id, which the messages it is told name it by.
    """

    def __init__(
        self,
        asks: Callable[[dict[str, Any], float | None], dict[str, Any]],
        leaves: Callable[[], None],
    ) -> None:
        """Holds the two halves of how this frontend reaches the runs.

        Made by :func:`linked` and :func:`reached`, which are what a frontend asks for one.

        Args:
          asks: What carries one request and brings back its answer.
          leaves: What lets go of the runs.
        """
        self.client = ""
        self._asks = asks
        self._leaves = leaves
        self._inbox: queue.SimpleQueue[dict[str, Any] | None] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._listener: Callable[[dict[str, Any]], None] | None = None
        self._closed = False

    def told(self, message: dict[str, Any]) -> None:
        """Takes one message on its way to this frontend. Called by whatever carries them."""
        self._inbox.put(message)

    def heard(self, listener: Callable[[dict[str, Any]], None]) -> None:
        """Hands every message from here on to `listener`, those already waiting first.

        On a thread of the link's own, in order: a listener that blocks holds up nothing but
        itself.

        Args:
          listener: What to hand each message to.

        Raises:
          RuntimeError: If this link already has one.
        """
        with self._lock:
            if self._listener is not None:
                raise RuntimeError("this link already has a listener")
            self._listener = listener

        def pumps() -> None:
            for message in self._messages():
                with contextlib.suppress(Exception):
                    listener(message)

        threading.Thread(
            target=pumps, daemon=True, name=f"humanize-link-{self.client}"
        ).start()

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Every message, in order, until the runs let this frontend go or it lets them go.

        Raises:
          RuntimeError: If a listener is taking them instead.
        """
        with self._lock:
            if self._listener is not None:
                raise RuntimeError("this link's messages go to its listener")
        return self._messages()

    def _messages(self) -> Iterator[dict[str, Any]]:
        while (message := self._inbox.get()) is not None:
            yield message
            if message.get("type") == "gone":
                return

    def asked(
        self, said: Mapping[str, Any], *, seconds: float | None = None
    ) -> dict[str, Any]:
        """Asks the runs one thing, and waits for the answer.

        Args:
          said: The request: `do`, and what that takes.
          seconds: How long to wait for the answer, or None for as long as it takes.

        Returns:
          The answer, which says `ok`.

        Raises:
          Refused: If it was refused, saying why.
          TimeoutError: If no answer came in time.
        """
        answer = self._asks(dict(said), seconds)
        if not answer.get("ok"):
            from hmz.runtime import Refused

            raise Refused(str(answer.get("why") or "refused"))
        return answer

    def start(
        self,
        flow: str | os.PathLike[str],
        task: str,
        *,
        agents: Mapping[str, Any] | None = None,
        envs: Mapping[str, Any] | None = None,
        params: Any = None,
        budget: Any = None,
        resume: bool | str | os.PathLike[str] = False,
    ) -> dict[str, Any]:
        """Starts a flow, which every frontend attached then reads.

        Args:
          flow: The flow, by the name it is offered under, a path, or a ref.
          task: What it is to do.
          agents: What each agent role runs, as `-a` spells it after `<role>=`.
          envs: What each environment role is, as `-e` spells it.
          params: The flow's params, as a mapping or its model, or None for its defaults.
          budget: What the run may spend, as a mapping or a `Budget`.
          resume: Whether to pick up the newest run of it, or the epic to pick up.

        Returns:
          The answer, with the run's number as `run`.
        """
        return self.asked(
            {
                "do": "start",
                "flow": str(flow),
                "task": task,
                "agents": dict(agents or {}),
                "envs": dict(envs or {}),
                "params": _plain(params),
                "budget": _plain(budget),
                "resume": resume if isinstance(resume, bool) else str(resume),
            }
        )

    def say(self, text: str, *, to: str = "") -> dict[str, Any]:
        """Says a line to the run: into the turn on view `to`, or the next one to start."""
        return self.asked({"do": "say", "text": text, "to": to})

    def answer(self, question: str, text: str) -> dict[str, Any]:
        """Answers one question an `Outworlder` is waiting on."""
        return self.asked({"do": "answer", "question": question, "text": text})

    def stop(self) -> dict[str, Any]:
        """Stops the run going: the turn under way is interrupted, and the flow unwinds."""
        return self.asked({"do": "stop"})

    def force(self) -> dict[str, Any]:
        """Closes every conversation of a run stopping, under whatever turn is open."""
        return self.asked({"do": "force"})

    def afk(self, *, on: bool, role: str = "") -> dict[str, Any]:
        """Says whether anybody is there for one `Outworlder` role, or for every one."""
        return self.asked({"do": "afk", "on": on, "role": role})

    def claim(self, role: str, *, take: bool = False) -> dict[str, Any]:
        """Holds one `Outworlder` role for this frontend alone, taking it where `take`."""
        return self.asked({"do": "claim", "role": role, "take": take})

    def release(self, role: str) -> dict[str, Any]:
        """Gives a role this frontend holds back to anybody."""
        return self.asked({"do": "release", "role": role})

    def board(self, key: str, value: str) -> dict[str, Any]:
        """Writes one line of the run's board, or takes it off with `value` empty."""
        return self.asked({"do": "board", "key": key, "value": value})

    def aside(self, **said: Any) -> dict[str, Any]:
        """Opens a side conversation, or takes one turn of one; see `aside` in the protocol."""
        return self.asked({"do": "aside", **said})

    def close(self) -> None:
        """Lets go of the runs, which go on without this frontend."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        with contextlib.suppress(Exception):
            self._leaves()
        self._inbox.put(None)

    def __enter__(self) -> Self:
        """Holds the link for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Lets go of the runs, however the block ended."""
        self.close()


def linked(
    host: Host, name: str = "", kind: str = "tui", *, replay: bool = True
) -> Link:
    """A frontend of runs held in this process.

    Args:
      host: The runs.
      name: What the frontend is called, or "" for whoever is at this end.
      kind: What it is: `tui`, `cli` or `sdk`.
      replay: Whether to be told the run so far, or only what happens from here.

    Returns:
      The link, attached.
    """
    held: list[str] = []

    def asks(said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        del seconds  # answered on this thread, however long it takes
        return host.asked(held[0], said)

    link = Link(asks, lambda: host.detach(held[0]))
    link.client = host.attach(name, kind, link.told, replay=replay)
    held.append(link.client)
    return link


class _Carried:
    """The socket a frontend reaches a host through, and the replies waiting on it."""

    def __init__(self, one: socket.socket) -> None:
        self._one = one
        self._lock = threading.Lock()
        self._sending = threading.Lock()
        self._ids = itertools.count(1)
        self._waiting: dict[str, tuple[threading.Event, list[dict[str, Any]]]] = {}
        self._gone = ""

    def start(self, told: Callable[[dict[str, Any]], None]) -> None:
        threading.Thread(
            target=self._reads, args=(told,), daemon=True, name="humanize-link"
        ).start()

    def asks(self, said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        rid = f"r{next(self._ids)}"
        landed = threading.Event()
        answered: list[dict[str, Any]] = []
        with self._lock:
            if self._gone:
                return {"ok": False, "why": self._gone}
            self._waiting[rid] = (landed, answered)
        try:
            written = json.dumps({**said, "id": rid}, default=str).encode()
            with self._sending:
                self._one.sendall(frame(MESSAGE, written))
        except OSError as why:
            with self._lock:
                self._waiting.pop(rid, None)
            return {"ok": False, "why": f"the host could not be reached: {why}"}
        if not landed.wait(seconds):
            with self._lock:
                self._waiting.pop(rid, None)
            raise TimeoutError(f"no answer to {said.get('do')!r} in {seconds}s")
        return answered[0]

    def leaves(self) -> None:
        with contextlib.suppress(OSError):
            self._one.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            self._one.close()

    def _reads(self, told: Callable[[dict[str, Any]], None]) -> None:
        """Reads the host until it closes, handing replies back and the rest on."""
        frames = Frames()
        why = "the host went away"
        said_gone = False
        try:
            while read := self._one.recv(_READ):
                for kind, payload in frames.feed(read):
                    message = asked(payload) if kind == MESSAGE else {}
                    if message.get("type") == "reply":
                        # Read after being let go of too: the answer to `detach` is owed.
                        self._answered(message)
                    elif said_gone:
                        continue
                    elif kind == GONE:
                        # A run held for a terminal, saying so.
                        why = payload.decode(errors="replace") or why
                        said_gone = True
                        told({"type": "gone", "why": why})
                    elif message:
                        told(message)
                        if message.get("type") == "gone":
                            why = str(message.get("why") or why)
                            said_gone = True
        except (OSError, ValueError):
            pass
        with self._lock:
            self._gone = why
            owed, self._waiting = list(self._waiting.values()), {}
        for landed, answered in owed:
            answered.append({"ok": False, "why": why})
            landed.set()
        if not said_gone:
            told({"type": "gone", "why": why})
        with contextlib.suppress(OSError):
            self._one.close()

    def _answered(self, message: dict[str, Any]) -> None:
        with self._lock:
            waiting = self._waiting.pop(str(message.get("to") or ""), None)
        if waiting is None:
            return
        landed, answered = waiting
        answered.append(
            {key: value for key, value in message.items() if key not in ("type", "to")}
        )
        landed.set()


def reached(
    at: Path, name: str = "", kind: str = "sdk", *, replay: bool = True
) -> Link:
    """A frontend of runs a host is holding, reached over its socket.

    Args:
      at: The daemon's own directory.
      name: What the frontend is called, or "" for whoever is at this end.
      kind: What it is: `tui`, `cli` or `sdk`.
      replay: Whether to be told the run so far, or only what happens from here.

    Returns:
      The link, attached.

    Raises:
      OSError: If nothing is listening there, or what is will not take a frontend -- a run
        held for a terminal says so rather than leaving this waiting.
    """
    import os

    from hmz.runtime import Refused

    one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with where.reached(at) as reaching:
            one.connect(reaching)
    except OSError:
        one.close()
        raise
    carried = _Carried(one)
    link = Link(carried.asks, carried.leaves)
    carried.start(link.told)
    # Named here rather than by the host: the host's process is not this one, and whoever
    # this end says it is, is this end's to say.
    user = os.environ.get("HUMANIZE_NAME", "")
    if not user:
        import getpass

        with contextlib.suppress(OSError, KeyError):
            user = getpass.getuser()
    try:
        said = link.asked(
            {
                "do": "hello",
                "name": name or f"{user or 'somebody'}@{kind}",
                "kind": kind,
                "replay": replay,
            },
            seconds=_PATIENCE,
        )
    except (Refused, TimeoutError) as why:
        carried.leaves()
        raise OSError(str(why)) from why
    link.client = str(said.get("client") or "")
    return link
