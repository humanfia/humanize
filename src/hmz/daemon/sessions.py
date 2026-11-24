"""One client's session with this machine's daemon, as the daemon holds it.

A session is a pipe -- the daemon's socket, or the mutual TLS or the WebRTC data channel over a
listener's carrier -- carrying the frames and the JSON-RPC of `hmz.rpc`. What the daemon keeps
of it besides is here: who the client is, whether its device is paired, the epic
subscriptions it holds, and the one queue of everything sent it (Section 6.10.1 of wire.md).

The daemon never waits on a session. What it sends is queued and written by a thread of the
session's own; once more than 64 MiB wait in the queue the notifications among them are
dropped, every response kept, and every subscription of the session ended -- an epic one with
`gone`, a notices one with `notices.event` saying so -- after the frame being written. That
includes one ended for an earlier fall behind whose end was still waiting and dropped with the
rest: its client would otherwise follow the subscription on, hearing nothing more of it.

A write that carries `idem` is carried out once per device (Section 6.7): :class:`Idems` keeps
each answer for 600 seconds, the latest 1 024 of each device.
"""

from __future__ import annotations

import collections
import contextlib
import json
import logging
import threading
import time
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.daemon.reach import Reach
    from hmz.rpc import Peer, Pipe

__all__ = ["BEHIND", "Idems", "Outgoing", "Session"]

_log = logging.getLogger(__name__)

#: How much may wait to be sent a session before it is too far behind.
BEHIND = 64 << 20

#: Why an epic subscription of a session too far behind is ended.
TOO_FAR = "too far behind; attach again"

#: Why a notices subscription of one is.
TOO_FAR_NOTICES = "too far behind; subscribe again"

#: What every notification's frame begins with, as `hmz.rpc` writes one: a response carries
#: `id` where a notification carries `method`.
_NOTIFIED = b'{"jsonrpc": "2.0", "method"'

#: How long an idempotent write's answer is kept, and how many of one device's are.
_KEPT = 600.0
_KEPT_MOST = 1024


class Outgoing:
    """A pipe whose writes are queued and written by a thread of its own.

    `hmz.rpc.Peer` writes one whole frame a call; each is queued here and the call returns at
    once, so that nothing the daemon does waits on a client that reads slowly.

    Args:
      pipe: What the frames go over.
      behind: Called once, off the lock, when more than :data:`BEHIND` waits: the
        notifications waiting have been dropped by then; those of them that ended a
        subscription are sent again by :meth:`again`.
    """

    def __init__(self, pipe: Pipe, behind: Callable[[], None]) -> None:
        self._pipe = pipe
        self._behind = behind
        self._lock = threading.Condition()
        self._waiting: collections.deque[tuple[bytes, bool]] = collections.deque()
        self._size = 0
        self._closed = False
        #: Whether everything queued so far is to be written before the pipe is closed.
        self._flushing = False
        #: Notices subscriptions ended for being behind, whose notifications go no further.
        self.ended: set[str] = set()
        #: What ended a subscription and was dropped as the session fell behind.
        self._lost: list[bytes] = []
        threading.Thread(target=self._writes, daemon=True, name="hmz-session").start()

    def recv(self, size: int, /) -> bytes:
        """What the client sent next."""
        return self._pipe.recv(size)

    def sendall(self, data: bytes, /) -> None:
        """Queues one frame.

        Raises:
          OSError: If the pipe is closed.
        """
        told = data[4 : 4 + len(_NOTIFIED)] == _NOTIFIED
        if told and self.ended and _sub(data) in self.ended:
            return
        with self._lock:
            if self._flushing:
                # Its last answer is on its way out: nothing after it is, nor fails.
                return
            if self._closed:
                raise BrokenPipeError("the session has closed")
            self._waiting.append((data, told))
            self._size += len(data)
            behind = self._size > BEHIND
            if behind:
                kept = [one for one in self._waiting if not one[1]]
                self._lost.extend(
                    one[0] for one in self._waiting if one[1] and _ends(one[0])
                )
                self._waiting = collections.deque(kept)
                self._size = sum(len(one[0]) for one in kept)
            self._lock.notify()
        if behind:
            # Off this thread, which may hold a subscription that ending them all waits on.
            threading.Thread(
                target=self._behind, daemon=True, name="hmz-behind"
            ).start()

    def again(self) -> None:
        """Queues again what ended a subscription and was dropped as the session fell behind.

        A subscription ended for an earlier fall behind is still one its client follows until
        it hears so, and is ended again with the same words (Section 6.10.1 of wire.md).
        """
        with self._lock:
            lost, self._lost = self._lost, []
            if self._closed or self._flushing:
                return
            for data in lost:
                self._waiting.append((data, True))
                self._size += len(data)
            self._lock.notify()

    def close(self) -> None:
        """Closes the pipe now, whatever is still queued."""
        with self._lock:
            self._closed = True
            self._waiting.clear()
            self._lock.notify()
        self._pipe.close()

    def flush_then_close(self) -> None:
        """Writes what is queued now, then closes the pipe; nothing queued after it is sent."""
        with self._lock:
            self._flushing = True
            self._lock.notify()

    def _writes(self) -> None:
        while True:
            with self._lock:
                while not self._waiting and not self._closed and not self._flushing:
                    self._lock.wait()
                if self._closed or not self._waiting:
                    break
                data, _ = self._waiting.popleft()
                self._size -= len(data)
            try:
                self._pipe.sendall(data)
            except OSError:
                break
        with contextlib.suppress(OSError):
            self._pipe.close()


def _ends(frame: bytes) -> bool:
    """Whether a notification's frame ends its subscription: an epic's `gone`, a notices' `gone`."""
    if b'"gone"' not in frame:
        return False
    try:
        said: object = json.loads(frame[4:])
    except ValueError:
        return False
    if not isinstance(said, dict):
        return False
    told = cast("dict[str, Any]", said)
    params: object = told.get("params")
    if not isinstance(params, dict):
        return False
    given = cast("dict[str, Any]", params)
    if told.get("method") == "notices.event":
        return "gone" in given
    message: object = given.get("message")
    return (
        told.get("method") == "epic.event"
        and isinstance(message, dict)
        and cast("dict[str, Any]", message).get("type") == "gone"
    )


def _sub(frame: bytes) -> str:
    """The `sub` a notification's frame names, or ""."""
    try:
        said: object = json.loads(frame[4:])
    except ValueError:
        return ""
    params: object = (
        cast("dict[str, Any]", said).get("params") if isinstance(said, dict) else None
    )
    sub: object = (
        cast("dict[str, Any]", params).get("sub") if isinstance(params, dict) else None
    )
    return sub if isinstance(sub, str) else ""


class Session:
    """One client's session, as the daemon keeps it.

    Attributes:
      peer: Its JSON-RPC end, set once it is made.
      out: The queue of what it is sent.
      trusted: Whether its carrier is.
      fingerprint: Its client's device fingerprint, `local` over a trusted carrier.
      device: The name its device is paired under, or "" while unpaired.
      name: The client's name, as `session.hello` said it.
      kind: What the client is, as `session.hello` said it.
      subs: Its epic subscriptions, by `sub`.
      notices: The notices subscriptions it opened, by `sub`.
      reach: The reach of the Ai-chan conversation whose scoped link it came over, or None
        (Section 4.21.1.1 of daemon.md).
    """

    def __init__(
        self,
        out: Outgoing,
        *,
        trusted: bool,
        fingerprint: str,
        device: str,
        reach: Reach | None = None,
    ) -> None:
        self.peer: Peer | None = None
        self.out = out
        self.trusted = trusted
        self.fingerprint = fingerprint
        self.device = device
        self.name = ""
        self.kind = ""
        self.lock = threading.Lock()
        self.subs: dict[str, Any] = {}
        self.notices: set[str] = set()
        self.reach = reach
        self._count = 0

    @property
    def paired(self) -> bool:
        """Whether the session is paired: its carrier is trusted, or its device was paired."""
        return bool(self.device)

    @property
    def closed(self) -> bool:
        """Whether the session has closed."""
        return self.peer is None or self.peer.closed

    def named(self) -> str:
        """A `sub` not given out before on this session."""
        with self.lock:
            self._count += 1
            return f"s{self._count}"

    def tell(self, method: str, params: dict[str, Any]) -> None:
        """Sends a notification, dropping it quietly where the session has closed."""
        from hmz.rpc import Closed

        if self.peer is not None:
            with contextlib.suppress(Closed):
                self.peer.notify(method, params)

    def close(self) -> None:
        """Closes the session now."""
        if self.peer is not None:
            self.peer.close()
        else:
            self.out.close()

    def behind(self) -> None:
        """Ends every subscription of a session that has fallen too far behind.

        Those ended by an earlier fall whose end was dropped with the rest first, in the order
        they were ended.
        """
        self.out.again()
        with self.lock:
            subs = list(self.subs.values())
            notices = list(self.notices)
            self.notices.clear()
        for sub in subs:
            sub.end(TOO_FAR)
        for one in notices:
            self.tell("notices.event", {"sub": one, "gone": TOO_FAR_NOTICES})
            self.out.ended.add(one)


class Idems:
    """The answers of the writes that carried `idem`, per device, each kept 600 seconds."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        #: Per device fingerprint, each `idem` to its method, its answer and when it came.
        self._kept: dict[
            str, collections.OrderedDict[str, tuple[str, Future[Any], float]]
        ]
        self._kept = {}

    def once(
        self, device: str, idem: str, method: str, doing: Callable[[], Any]
    ) -> Any:
        """Carries a write out once per device and key, and answers each call of it alike.

        Args:
          device: The calling session's device fingerprint.
          idem: The key the write carried.
          method: The write.
          doing: What carries it out.

        Returns:
          What the first call of it answered.

        Raises:
          RpcError: What the first call of it was refused with, or 409 where the key was used
            for another method.
        """
        from hmz.rpc import Code, RpcError

        now = self._clock()
        with self._lock:
            kept = self._kept.setdefault(device, collections.OrderedDict())
            for key in [k for k, (_, _, at) in kept.items() if now - at > _KEPT]:
                del kept[key]
            held = kept.get(idem)
            if held is None:
                future: Future[Any] = Future()
                kept[idem] = (method, future, now)
                while len(kept) > _KEPT_MOST:
                    kept.popitem(last=False)
                mine = True
            else:
                if held[0] != method:
                    raise RpcError(
                        Code.CONFLICT, "That idem key was used for another method."
                    )
                future, mine = held[1], False
        if mine:
            try:
                future.set_result(doing())
            except RpcError as why:
                future.set_exception(why)
            except Exception as why:
                future.set_exception(why)
                raise
        return future.result()
