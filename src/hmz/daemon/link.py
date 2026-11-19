"""One frontend's end of a workspace's runs: requests out, and messages about the runs in.

A frontend -- an interface or a program -- reaches the runs of a workspace through this
machine's daemon: a session of `protocol/wire.md` over its socket, saying `session.hello` and
then `epic.attach`, whose `epic.event` notifications are the messages and whose calls to the
epic are the requests (Section 4.18 of python.md). What is said to a chat is said by `chat.*`
(Section 4.25 of daemon.md) of the workspace and slot attached to, rather than to the epic. A
frontend still holding runs in its own process (:func:`linked`) is handed the same
:class:`Link`, so that it is written once.

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

#: The calls to a chat that are writes, which carry an `idem` of their own.
_CHAT_WRITES = frozenset({"chat.start", "chat.say", "chat.set", "chat.stop"})

#: The calls to an environment of the epic that are writes, which carry an `idem` too. An
#: `env.*` call is named as it is, rather than as one more `epic.<do>`: it is a method of its
#: own, made with the epic's `sub` as every call to the epic is.
_ENV_WRITES = frozenset(
    {
        "env.write",
        "env.mkdir",
        "env.rename",
        "env.remove",
        "env.git.stage",
        "env.git.unstage",
        "env.git.discard",
        "env.git.commit",
        "env.git.rewind",
    }
)


def _method(do: str) -> str:
    """The method one request is: `env.*` as it is, anything else the epic's `epic.<do>`."""
    return do if do.startswith("env.") else f"epic.{do}"


def _no(why: str, code: int, data: dict[str, Any] | None) -> dict[str, Any]:
    """A refusal as the daemon said it: why, its code, and its data where it has any."""
    return {
        "ok": False,
        "why": why,
        "code": code,
        **({"data": data} if data is not None else {}),
    }


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

            code, data = answer.get("code"), answer.get("data")
            raise Refused(
                str(answer.get("why") or "refused"),
                code=code if isinstance(code, int) else 0,
                data=cast("dict[str, Any]", data) if isinstance(data, dict) else None,
            )
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

    def answer(
        self, question: str, text: str | None = None, value: Any = None
    ) -> dict[str, Any]:
        """Answers one question an `Outworlder` is waiting on, in text or as a value.

        Args:
          question: The question, by its id.
          text: The answer typed: an option, its number, words, or the JSON of a value.
          value: The answer as the value of the question's schema, given in place of `text`.

        Returns:
          The answer, which says `ok`.

        Raises:
          Refused: If it was refused: a value that does not fit is refused 400, with every
            way it does not as `data["errors"]`.
        """
        if text is None:
            return self.asked({"do": "answer", "question": question, "value": value})
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

    def chat(
        self,
        agent: str,
        task: str,
        *,
        resume: str | os.PathLike[str] | None = None,
        prefer: str | None = None,
        permission: str | None = None,
        remember: bool = False,
        worktree: bool = False,
    ) -> dict[str, Any]:
        """Starts a chat on the chat host this frontend is attached to, or carries one on.

        Args:
          agent: The assistant, as `-a` spells an agent after `<role>=`; "" for a chat
            carried on, to go on with its own.
          task: Its first message.
          resume: The name of a chat of this workspace to carry on, or None for a new one.
          prefer: `native` or `flow`, this chat's own preference, or None for the setting.
          permission: `read-only`, `workspace-write` or `danger-full-access`, what its
            assistant may touch, or None for `workspace-write`, or what a chat carried on had.
          remember: Whether to remember `agent` as the workspace's chat agent.
          worktree: Whether a new chat's assistant works in a new git worktree of the
            workspace.

        Returns:
          The answer, with the chat's `slot` and, as `chat`, its name.
        """
        return self.asked(
            {
                "do": "chat.start",
                "agent": agent,
                "task": task,
                "resume": None if resume is None else str(resume),
                "prefer": prefer,
                "permission": permission,
                "remember": remember,
                "worktree": worktree,
            }
        )

    def chat_say(self, text: str) -> dict[str, Any]:
        """Says one line to the chat: its next message, an answer, or "" to end it."""
        return self.asked({"do": "chat.say", "text": text})

    def chat_stop(self) -> dict[str, Any]:
        """Stops the chat's open turn, leaving the chat between turns."""
        return self.asked({"do": "chat.stop"})

    def chat_commands(self) -> dict[str, Any]:
        """What a line of the chat can start with, and what its `$` names prefer."""
        return self.asked({"do": "chat.commands"})

    def chat_set(
        self, prefer: str | None = None, *, permission: str | None = None
    ) -> dict[str, Any]:
        """Sets the chat's own preference, its permission, or both.

        Args:
          prefer: `native` or `flow`, for a `$` name that is both, or None to leave it.
          permission: `read-only`, `workspace-write` or `danger-full-access`, what its
            assistant may touch from its next turn on, or None to leave it.
        """
        said = {"prefer": prefer, "permission": permission}
        return self.asked(
            {"do": "chat.set"}
            | {key: value for key, value in said.items() if value is not None}
        )

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
    #: The slot attached to, which a chat's calls name.
    slotted: list[str] = []

    def asks(said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        do = str(said.pop("do", ""))
        if gone:
            return {"ok": False, "why": gone[0]}
        if do.startswith("chat."):
            method = do
            params = {**said, "workspace": workspace, "slot": slotted[0]}
            if do in _CHAT_WRITES:
                params["idem"] = secrets.token_urlsafe(12)
        else:
            method = _method(do)
            params = {**said, "sub": sub[0]}
            if do in _WRITES or do in _ENV_WRITES:
                params["idem"] = secrets.token_urlsafe(12)
        try:
            pending = peer.request(method, params)
        except (Closed, OSError) as why:
            return {"ok": False, "why": f"the host could not be reached: {why}"}
        except RpcError as why:
            return _no(why.message, why.code, why.data)
        try:
            result: Any = pending.result(seconds)
        except TimeoutError:
            with contextlib.suppress(Closed):
                pending.cancel()
            raise TimeoutError(f"no answer to {do!r} in {seconds}s") from None
        except RpcError as why:
            return _no(why.message, why.code, why.data)
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
            # Starting a host is a fork and its handshake, each given as long.
            timeout=_PATIENCE * 3,
        )
    except (RpcError, Closed, TimeoutError) as why:
        peer.close()
        raise OSError(str(why) or type(why).__name__) from why
    link.client = str(attached.get("client") or "")
    slotted.append(str(attached.get("slot") or slot))
    with lock:
        sub.append(str(attached["sub"]))
        for named, told in early:
            if named == sub[0]:
                delivers(told)
        early.clear()

    threading.Thread(target=ends, daemon=True, name="hmz-link-ends").start()
    return link


#: How often a link to another machine's daemon looks whether it was left.
_LEFT = 0.5


def remote(remotes: Remotes, daemon: str, workspace: str, slot: str = "") -> Link:
    """A frontend of the runs of one workspace on another machine, through its daemon.

    The session the daemons of other machines are reached by (`Remotes.client`), and
    `epic.attach` over it, as :func:`reached` attaches over this machine's socket: its
    `epic.event` notifications are the messages and its calls to the epic the requests.

    Args:
      remotes: The daemons of other machines, as they are reached here.
      daemon: Which, by name.
      workspace: The workspace there whose runs these are.
      slot: Which of its hosts: "" for its own, `chat:<hex>` for a chat's.

    Returns:
      The link, attached.

    Raises:
      OSError: If that daemon is not reached, or would not attach.
    """
    from hmz.runtime import Refused

    try:
        client = remotes.client(daemon)
    except (RuntimeError, LookupError) as why:
        raise OSError(str(why)) from why
    held: list[Link] = []
    early: list[tuple[object, dict[str, Any]]] = []
    gone: list[str] = []
    sub: list[str] = []
    lock = threading.Lock()

    def delivers(told: dict[str, Any]) -> None:
        if told.get("type") == "gone":
            gone.append(str(told.get("why") or _WENT))
        held[0].told(told)

    def heard(method: str, params: dict[str, Any]) -> None:
        message = params.get("message")
        if method != "epic.event" or not isinstance(message, dict):
            return
        told = dict(cast("dict[str, Any]", message))
        with lock:
            if not sub:
                early.append((params.get("sub"), told))
            elif params.get("sub") == sub[0]:
                delivers(told)

    #: The slot attached to, which a chat's calls name.
    slotted: list[str] = []

    def asks(said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        do = str(said.pop("do", ""))
        if gone:
            return {"ok": False, "why": gone[0]}
        if do.startswith("chat."):
            method, params = do, {**said, "workspace": workspace, "slot": slotted[0]}
            idem = secrets.token_urlsafe(12) if do in _CHAT_WRITES else None
        else:
            method, params = _method(do), {**said, "sub": sub[0]}
            idem = (
                secrets.token_urlsafe(12)
                if do in _WRITES or do in _ENV_WRITES
                else None
            )
        try:
            result: Any = client.call(method, params, idem=idem, seconds=seconds)
        except Refused as why:
            if gone:
                return {"ok": False, "why": gone[0]}
            return _no(str(why), why.code, why.data)
        return {"ok": True, **(result if isinstance(result, dict) else {})}

    left = threading.Event()

    def leaves() -> None:
        left.set()
        with contextlib.suppress(Refused, TimeoutError):
            client.call("epic.detach", {"sub": sub[0]}, seconds=_PATIENCE)
        client.close()

    link = Link(asks, leaves)
    held.append(link)
    client.heard(heard)
    try:
        attached: Any = client.call(
            "epic.attach",
            {"workspace": workspace, "slot": slot, "replay": True},
            seconds=_PATIENCE * 3,
        )
    except (Refused, TimeoutError) as why:
        client.close()
        raise OSError(str(why)) from why
    link.client = str(attached.get("client") or "")
    slotted.append(str(attached.get("slot") or slot))
    with lock:
        sub.append(str(attached["sub"]))
        for named, told in early:
            if named == sub[0]:
                delivers(told)
        early.clear()

    def ends() -> None:
        # The session is the daemon's, which outlives this link.
        while not client.wait(_LEFT):
            if left.is_set():
                return
        if not gone:
            gone.append(_WENT)
            link.told({"type": "gone", "why": _WENT})

    threading.Thread(target=ends, daemon=True, name="hmz-link-ends").start()
    return link
