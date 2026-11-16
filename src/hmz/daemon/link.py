"""One frontend's end of a workspace's runs: requests out, and messages about the runs in.

A frontend -- an interface or a program -- reaches the runs of a workspace through this
machine's daemon: a session of `protocol/wire.md` over its socket, saying `session.hello` and
then `epic.attach`, whose `epic.event` notifications are the messages and whose calls to the
epic are the requests (Section 4.18 of python.md). A frontend still holding runs in its own
process (:func:`linked`) is handed the same :class:`Link`, so that it is written once.

What it is told arrives in order, on a thread that is not the caller's: handed to a listener
once one is set, and read by iterating the link until then. What it asks is answered on the
thread that asked, one request one reply, with a refusal raised as the runtime's own
:class:`hmz.runtime.Refused` and in the same words whichever way it was reached.
"""

from __future__ import annotations

import contextlib
import json
import queue
import secrets
import threading
from typing import TYPE_CHECKING, Any, Self, cast

from hmz.daemon import where

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable, Iterator, Mapping
    from pathlib import Path
    from types import TracebackType

    from hmz.rpc import Call, Peer
    from hmz.runtime import Host
    from hmz.runtime.doing.daemons import Remotes

__all__ = ["Link", "dialed", "linked", "reached", "remote"]

#: How long the daemon is given to say hello back and attach.
_PATIENCE = 10.0

#: The calls to an epic that are writes, which carry an `idem` of their own.
_WRITES = frozenset(
    {
        "start",
        "say",
        "answer",
        "stop",
        "force",
        "afk",
        "claim",
        "release",
        "board",
        "quit",
    }
)

#: Why a link whose session ended without a `gone` is let go.
_WENT = "the host went away"


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
        profile_flow: bool = False,
        profile_environment: bool = False,
        resume: bool | str | os.PathLike[str] = False,
        backup: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Starts a flow, which every frontend attached then reads.

        Args:
          flow: The flow, by the name it is offered under, a path, or a ref.
          task: What it is to do.
          agents: What each agent role runs, as `-a` spells it after `<role>=`.
          envs: What each environment role is, as `-e` spells it.
          params: The flow's params, as a mapping or its model, or None for its defaults.
          budget: What the run may spend, as a mapping or a `Budget`.
          profile_flow: Whether to sample the flow's own Python while it runs.
          profile_environment: Whether to profile the programs its agents start, as well as
            trace them.
          resume: Whether to pick up the newest run of it, or the epic to pick up.
          backup: The backup targets its epic goes to, by name, or None for the defaults.

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
                "profile_flow": profile_flow,
                "profile_environment": profile_environment,
                "resume": resume if isinstance(resume, bool) else str(resume),
                "backup": None if backup is None else list(backup),
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


def dialed(
    at: Path,
    name: str = "",
    kind: str = "sdk",
    *,
    serve: Callable[[Call], None] | None = None,
    seconds: float = _PATIENCE,
) -> tuple[Peer, dict[str, Any]]:
    """A session with this machine's daemon over its socket, hello said.

    Args:
      at: The daemon's directory.
      name: What the client is called, "" for nothing.
      kind: What it is: `tui`, `web`, `cli`, `sdk`.
      serve: What each notification the daemon sends is handed to.
      seconds: How long the daemon is given to answer hello.

    Returns:
      The session, and what `session.hello` answered.

    Raises:
      OSError: If nothing is listening there, it did not answer, or it refused this
        client's protocol -- `EADDRINUSE`, with the refusal's message.
    """
    import errno

    from hmz.reach.pipes import SocketPipe
    from hmz.rpc import Closed, Code, Peer, RpcError, hello

    one = where.connects(at, seconds)
    one.settimeout(None)
    peer = Peer(SocketPipe(one, trusted=True), serve, name="hmz-link")
    try:
        said = hello(peer, name, kind, timeout=seconds)  # pyright: ignore[reportArgumentType]
    except RpcError as why:
        peer.close()
        if why.code == Code.PROTOCOL_MISMATCH:
            raise OSError(errno.EADDRINUSE, why.message) from why
        raise OSError(why.message) from why
    except (Closed, TimeoutError) as why:
        peer.close()
        raise OSError(f"the daemon did not say hello: {why}") from why
    return peer, said


def _named(name: str, kind: str) -> str:
    """What a frontend is called: its name, or whoever is at this end and its kind."""
    import os

    if name:
        return name
    user = os.environ.get("HUMANIZE_NAME", "")
    if not user:
        import getpass

        with contextlib.suppress(OSError, KeyError):
            user = getpass.getuser()
    return f"{user or 'somebody'}@{kind}"


def reached(
    at: Path,
    workspace: str,
    name: str = "",
    kind: str = "sdk",
    *,
    replay: bool = True,
    slot: str = "",
) -> Link:
    """A frontend of runs a host is holding, reached through this machine's daemon.

    Opens a session, says `session.hello`, and calls `epic.attach` (Section 4.17.3 of
    python.md): the daemon starts the workspace's host where none is.

    Args:
      at: The daemon's directory.
      workspace: The workspace whose runs these are, as :func:`hmz.daemon.where.workspace`
        says it.
      name: What the frontend is called, or "" for whoever is at this end.
      kind: What it is: `tui`, `cli`, `web` or `sdk`.
      replay: Whether to be told the run so far, or only what happens from here.
      slot: Which of the workspace's hosts: "" for its own, `chat:<hex>` for a chat's.

    Returns:
      The link, attached.

    Raises:
      OSError: If nothing is listening there, or `session.hello` or `epic.attach` was refused
        or not answered in time.
    """
    from hmz.rpc import Closed, RpcError

    held: list[Link] = []
    #: What arrived before the daemon's answer to `epic.attach` was read, by `sub`.
    early: list[tuple[object, dict[str, Any]]] = []
    gone: list[str] = []
    sub: list[str] = []
    lock = threading.Lock()

    def delivers(told: dict[str, Any]) -> None:
        if told.get("type") == "gone":
            gone.append(str(told.get("why") or _WENT))
        held[0].told(told)

    def heard(call: Call) -> None:
        message = call.params.get("message")
        if call.method != "epic.event" or not isinstance(message, dict):
            return
        told = dict(cast("dict[str, Any]", message))
        with lock:
            if not sub:
                early.append((call.params.get("sub"), told))
            elif call.params.get("sub") == sub[0]:
                delivers(told)

    peer, _ = dialed(at, _named(name, kind), kind, serve=heard)

    def asks(said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        do = str(said.pop("do", ""))
        if gone:
            return {"ok": False, "why": gone[0]}
        params = {**said, "sub": sub[0]}
        if do in _WRITES:
            params["idem"] = secrets.token_urlsafe(12)
        try:
            pending = peer.request(f"epic.{do}", params)
        except (Closed, OSError) as why:
            return {"ok": False, "why": f"the host could not be reached: {why}"}
        except RpcError as why:
            return {"ok": False, "why": why.message}
        try:
            result: Any = pending.result(seconds)
        except TimeoutError:
            with contextlib.suppress(Closed):
                pending.cancel()
            raise TimeoutError(f"no answer to {do!r} in {seconds}s") from None
        except RpcError as why:
            return {"ok": False, "why": why.message}
        except Closed:
            return {"ok": False, "why": gone[0] if gone else _WENT}
        return {"ok": True, **(result if isinstance(result, dict) else {})}

    link = Link(asks, peer.close)
    held.append(link)

    def ends() -> None:
        peer.wait()
        if not gone:
            gone.append(_WENT)
            link.told({"type": "gone", "why": _WENT})

    try:
        attached: Any = peer.call(
            "epic.attach",
            {"workspace": workspace, "slot": slot, "replay": replay},
            timeout=_PATIENCE,
        )
    except (RpcError, Closed, TimeoutError) as why:
        peer.close()
        raise OSError(str(why) or type(why).__name__) from why
    link.client = str(attached.get("client") or "")
    with lock:
        sub.append(str(attached["sub"]))
        for named, told in early:
            if named == sub[0]:
                delivers(told)
        early.clear()

    threading.Thread(target=ends, daemon=True, name="hmz-link-ends").start()
    return link


#: How long another machine's interface is given to say who this end is.
_HELLO = 30.0


def remote(remotes: Remotes, daemon: str, workspace: str, slot: str = "") -> Link:
    """A frontend of the runs of one workspace on another machine, through its web interface.

    What its web page reaches them by, reached over ssh: what is asked is posted as the page
    posts it, and what the runs say is the page's stream of them, records and how each thing
    stands, told to this end in order. It reads them as that interface's own page does, and
    answers as that interface.

    Args:
      remotes: The daemons of other machines, as they are reached here.
      daemon: Which, by name.
      workspace: The workspace there whose runs these are.
      slot: Which of its hosts: "" for its own, `chat:<hex>` for a chat's.

    Returns:
      The link, following them.

    Raises:
      OSError: If that machine's interface would not say who this end is.
    """
    from urllib.parse import quote

    from hmz.runtime.doing.daemons import Unreached

    going = threading.Event()
    hello: queue.SimpleQueue[str | BaseException] = queue.SimpleQueue()

    def asks(said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        del seconds  # as long as that interface takes, which bounds it itself
        do = str(said.pop("do"))
        try:
            answer = remotes.asked(
                daemon,
                f"/api/held/{quote(do)}",
                {**said, "workspace": workspace, "slot": slot},
            )
        except (Unreached, LookupError, OSError) as why:
            return {"ok": False, "why": str(why)}
        return {"ok": True, **(answer if isinstance(answer, dict) else {})}

    link = Link(asks, going.set)

    def follows() -> None:
        why = f"{daemon} stopped saying how its runs stand"
        try:
            stream = f"/api/held/stream?workspace={quote(workspace)}"
            for event, data in remotes.followed(
                daemon, f"{stream}&slot={quote(slot)}" if slot else stream, going
            ):
                if event == "hello":
                    hello.put(str(data.get("me") or ""))
                elif event in ("record", "standing"):
                    link.told(data)
                elif event == "gone":
                    why = str(data.get("why") or why)
                    break
                elif event == "again":
                    why = f"{daemon} let its runs go and took them again"
                    break
        except (Unreached, LookupError, OSError, ValueError) as error:
            why = str(error)
            hello.put(error)
        if not going.is_set():
            link.told({"type": "gone", "why": why})

    threading.Thread(target=follows, daemon=True, name="humanize-remote").start()
    try:
        me = hello.get(timeout=_HELLO)
    except queue.Empty as why:
        going.set()
        raise OSError(f"{daemon} did not say who this end is") from why
    if isinstance(me, BaseException):
        raise OSError(str(me)) from me
    link.client = me
    return link
