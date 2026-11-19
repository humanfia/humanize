"""One end of a JSON-RPC 2.0 session (Section 6.4 of wire.md), over any :class:`Pipe`.

Either end may make calls and send notifications, and either answers what the other makes:
the protocol has the daemon make no calls (Section 6.4.2), which is the daemon's to keep to,
and a peer is the same object at both ends. A call carries an integer `id` this end has not
used before on the session, so no `id` is ever in use twice (Section 6.4.3), and is answered
by the response bearing it, in whatever order the other end answers (Section 6.4.4).

A peer reads its pipe on a thread of its own, and hands each call and notification that
arrives to the `serve` it was made with, on that thread and in the order they arrived; what
`serve` does with a call -- answer it at once, or on another thread later -- is its own, and
:class:`hmz.rpc.Dispatcher` is the one this package offers. `session.cancel` is the peer's
own: it marks the call it names cancelled, which the code carrying that call out reads and
gives up on by answering -32800, or carries on regardless (Section 6.4.7).

The session ends when either end closes its pipe, when a frame arrives of a length no frame
has (Section 6.3.2), or when :meth:`Peer.close` is called; each call still waiting for an
answer then fails with :class:`Closed`, and each call being carried out is marked cancelled.
Where it was the pipe failing that ended it, that failure is the `__cause__` of the
:class:`Closed`, of a call waiting and of one made later alike: what a carrier that ended badly
said, such as the last line of its process.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import logging
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, cast

from typing_extensions import TypeIs

from hmz.rpc.errors import Closed, Code, RpcError
from hmz.rpc.frames import FrameError, Frames, encode

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.rpc.pipe import Pipe

__all__ = ["Call", "Peer", "Pending"]

_log = logging.getLogger(__name__)

#: How much one read of the pipe asks for.
_READ = 1 << 16


def _is_id(value: object) -> TypeIs[str | int]:
    """Whether a value is an `id` a call may carry: a text or an integer (Section 6.4.3)."""
    return isinstance(value, str) or (
        isinstance(value, int) and not isinstance(value, bool)
    )


def _not_json(constant: str) -> object:
    """Refuses `NaN` and the infinities, which Python's reader takes and JSON does not have."""
    raise ValueError(f"{constant} is not JSON")


class Call:
    """A call or a notification the other end made, as it is handed to `serve`.

    Attributes:
      peer: The end it arrived at, which an answer goes out of.
      method: The method it names.
      params: Its parameters by name; empty where it carried none.
      id: Its `id`, or `None` for a notification, which is never answered.
      cancelled: Set once the other end asks for the call to be given up, or the session
        closes; the code carrying it out reads it and answers -32800 where it gives up.
    """

    def __init__(
        self,
        peer: Peer,
        method: str,
        params: dict[str, Any],
        ident: str | int | None,
        send: Callable[[Call, dict[str, Any]], None],
    ) -> None:
        self.peer = peer
        self.method = method
        self.params = params
        self.id = ident
        self.cancelled = threading.Event()
        self._send = send

    def answer(self, result: Any) -> None:
        """Answers the call with a result; only its first answer is sent, and none after close."""
        self._send(self, {"result": result})

    def fail(self, error: RpcError) -> None:
        """Answers the call with an error; only its first answer is sent, and none after close."""
        self._send(self, {"error": error.to_json()})


class Pending:
    """A call this end made, waiting for its answer.

    Attributes:
      id: The `id` it carries.
    """

    def __init__(self, peer: Peer, ident: int, future: Future[Any]) -> None:
        self.id = ident
        self._peer = peer
        self._future = future

    def result(self, timeout: float | None = None) -> Any:
        """Waits for the answer.

        Args:
          timeout: How many seconds to wait, or `None` for as long as it takes.

        Returns:
          The call's result.

        Raises:
          RpcError: If the call was answered with an error.
          Closed: If the session closed before it was answered.
          TimeoutError: If `timeout` passed first; the call is still waiting.
        """
        return self._future.result(timeout)

    def cancel(self) -> None:
        """Asks the other end to give the call up, with `session.cancel` (Section 6.4.7).

        The call is still waiting afterwards: the other end answers it either way, with -32800
        where it gave it up.

        Raises:
          Closed: If the session has closed.
        """
        self._peer.notify("session.cancel", {"id": self.id})


class Peer:
    """One end of a JSON-RPC 2.0 session over a pipe, reading it from the moment it is made.

    Args:
      pipe: What the frames go over.
      serve: What each call and notification the other end makes is handed to, on the peer's
        reading thread and in the order they arrived; `None` answers every call with -32601
        and ignores every notification.
      on_close: Called once, on whichever thread closes the session, after every waiting call
        has failed.
      name: What the reading thread is named.
    """

    def __init__(
        self,
        pipe: Pipe,
        serve: Callable[[Call], None] | None = None,
        *,
        on_close: Callable[[], None] | None = None,
        name: str = "hmz-rpc",
    ) -> None:
        self._pipe = pipe
        self._serve = serve
        self._on_close = on_close
        #: What else is told the session closed, as `closing` was given it.
        self._closing: list[Callable[[], None]] = []
        #: Guards what follows, and makes closing and registering a call one or the other.
        self._lock = threading.Lock()
        #: One frame written at a time, whichever thread writes it.
        self._writing = threading.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[int, Future[Any]] = {}
        self._serving: dict[str | int, Call] = {}
        self._closed = threading.Event()
        #: What the pipe raised as it was read, where that is what ended the session.
        self._why: OSError | None = None
        self._reader = threading.Thread(target=self._read, name=name, daemon=True)
        self._reader.start()

    @property
    def closed(self) -> bool:
        """Whether the session has closed."""
        return self._closed.is_set()

    def closing(self, told: Callable[[], None]) -> None:
        """Has the session's closing told to a callback: once, at once where it has closed.

        What keeps something for the session -- a subscription -- lets go of it here.

        Args:
          told: Called once, on whichever thread closes the session, after `on_close`.
        """
        with self._lock:
            if not self.closed:
                self._closing.append(told)
                return
        told()

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the session to close, and says whether it has."""
        return self._closed.wait(timeout)

    def request(self, method: str, params: dict[str, Any] | None = None) -> Pending:
        """Makes a call, and gives back what waits for its answer.

        Args:
          method: The method to call.
          params: Its parameters by name, or `None` to send none.

        Returns:
          The call, waiting.

        Raises:
          RpcError: 413, if the call is more than a frame may carry; it is not sent.
          Closed: If the session has closed.
        """
        ident = next(self._ids)
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": ident, "method": method}
        if params is not None:
            message["params"] = params
        try:
            frame = encode(message)
        except FrameError:
            raise RpcError(
                Code.TOO_LARGE, "That is more than a call here may carry."
            ) from None
        future: Future[Any] = Future()
        with self._lock:
            if self.closed:
                raise Closed("the session has closed") from self._why
            self._pending[ident] = future
        self._write(frame)
        return Pending(self, ident, future)

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        """Makes a call and waits for its result.

        Args:
          method: The method to call.
          params: Its parameters by name, or `None` to send none.
          timeout: How many seconds to wait, or `None` for as long as it takes. Where it
            passes, the call is given up here and the other end is asked to give it up too.

        Returns:
          The call's result.

        Raises:
          RpcError: If the call was answered with an error, or was too large to send.
          Closed: If the session closed before it was answered.
          TimeoutError: If `timeout` passed first.
        """
        pending = self.request(method, params)
        try:
            return pending.result(timeout)
        except TimeoutError:
            with self._lock:
                self._pending.pop(pending.id, None)
            with contextlib.suppress(Closed):
                pending.cancel()
            raise

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Sends a notification, which is never answered.

        One more than a frame may carry is dropped and logged rather than sent (Section
        6.10.2).

        Args:
          method: The notification's method.
          params: Its parameters by name, or `None` to send none.

        Raises:
          Closed: If the session has closed.
        """
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        try:
            frame = encode(message)
        except FrameError:
            _log.warning("dropped %s: more than a frame may carry", method)
            return
        self._write(frame)

    def close(self) -> None:
        """Closes the session: its pipe, every call waiting, every call being carried out.

        Closing a session already closed does nothing.
        """
        with self._lock:
            if self.closed:
                return
            self._closed.set()
            pending = list(self._pending.values())
            self._pending.clear()
            serving = list(self._serving.values())
            self._serving.clear()
        with contextlib.suppress(OSError):
            self._pipe.close()
        for waiting in pending:
            closed = Closed("the session closed")
            closed.__cause__ = self._why
            waiting.set_exception(closed)
        for call in serving:
            call.cancelled.set()
        if self._on_close is not None:
            self._on_close()
        with self._lock:
            closing, self._closing = self._closing, []
        for told in closing:
            told()

    def _write(self, frame: bytes) -> None:
        """Writes one frame, closing the session where the pipe will not take it."""
        if self.closed:
            raise Closed("the session has closed") from self._why
        try:
            with self._writing:
                self._pipe.sendall(frame)
        except OSError as e:
            self.close()
            # What the read was told first is why, where the pipe took no more for it.
            raise Closed("the session closed") from (self._why or e)

    def _answer(self, call: Call, answer: dict[str, Any]) -> None:
        """Sends a call's one answer, and nothing for a notification or a call answered."""
        if call.id is None:
            return
        with self._lock:
            if self._serving.get(call.id) is not call:
                return
            del self._serving[call.id]
        self._respond(call.id, answer)

    def _respond(self, ident: str | int | None, answer: dict[str, Any]) -> None:
        """Sends a response, swapping a result too large to carry for 413 (Section 6.10.2).

        A result JSON cannot hold is answered -32603, so that the call is still answered once.
        """
        try:
            frame = encode({"jsonrpc": "2.0", "id": ident, **answer})
        except FrameError:
            error = RpcError(
                Code.TOO_LARGE, "That is more than an answer here may carry."
            )
            frame = encode({"jsonrpc": "2.0", "id": ident, "error": error.to_json()})
        except (TypeError, ValueError) as e:
            _log.exception("answering %s failed", ident)
            error = RpcError.unanticipated(e)
            frame = encode({"jsonrpc": "2.0", "id": ident, "error": error.to_json()})
        with contextlib.suppress(Closed):
            self._write(frame)

    def _refuse(self, ident: str | int | None, code: Code, message: str) -> None:
        self._respond(ident, {"error": RpcError(code, message).to_json()})

    def _read(self) -> None:
        """Reads the pipe until it ends, handing on each frame that arrives."""
        frames = Frames()
        try:
            while not self.closed:
                data = self._pipe.recv(_READ)
                if not data:
                    break
                for payload in frames.feed(data):
                    self._take(payload)
        except FrameError as e:
            for payload in e.whole:
                self._take(payload)
        except OSError as why:
            self._why = why
        finally:
            self.close()

    def _take(self, payload: bytes) -> None:
        """Takes one frame's payload: a call, a notification or a response."""
        try:
            message: object = json.loads(payload, parse_constant=_not_json)
        except (ValueError, RecursionError):
            self._refuse(None, Code.PARSE_ERROR, "Send JSON.")
            return
        if isinstance(message, list):
            self._refuse(None, Code.INVALID_REQUEST, "Send one request a frame.")
            return
        said = cast("dict[str, Any]", message) if isinstance(message, dict) else {}
        if said.get("jsonrpc") != "2.0":
            self._refuse(
                None, Code.INVALID_REQUEST, "That is not a JSON-RPC 2.0 request."
            )
            return
        if "method" in said:
            self._called(said)
        elif "id" in said and ("result" in said or "error" in said):
            self._answered(said)
        else:
            self._refuse(
                None, Code.INVALID_REQUEST, "That is not a JSON-RPC 2.0 request."
            )

    def _called(self, said: dict[str, Any]) -> None:
        """Takes a call or a notification, and hands it to `serve`."""
        method, params = said["method"], said.get("params", {})
        ident = said.get("id")
        well_formed = isinstance(method, str) and isinstance(params, dict)
        if "id" not in said:
            if not well_formed:
                return
            given = cast("dict[str, Any]", params)
            if method == "session.cancel":
                self._cancelled(given.get("id"))
            elif self._serve is not None:
                self._hand(Call(self, method, given, None, self._answer))
            return
        if not _is_id(ident):
            self._refuse(
                None, Code.INVALID_REQUEST, "That is not a JSON-RPC 2.0 request."
            )
            return
        if not well_formed:
            self._refuse(
                ident, Code.INVALID_REQUEST, "That is not a JSON-RPC 2.0 request."
            )
            return
        given = cast("dict[str, Any]", params)
        call = Call(self, method, given, ident, self._answer)
        with self._lock:
            if self.closed:
                return
            busy = ident in self._serving
            if not busy:
                self._serving[ident] = call
        if busy:
            self._refuse(
                None, Code.INVALID_REQUEST, "That id is in use by another call."
            )
        elif self._serve is None:
            call.fail(RpcError(Code.METHOD_NOT_FOUND, f"There is no method {method}."))
        else:
            self._hand(call)

    def _hand(self, call: Call) -> None:
        """Hands a call to `serve`, answering it -32603 where `serve` itself fails."""
        if self._serve is None:
            return
        try:
            self._serve(call)
        except Exception as e:  # noqa: BLE001 -- a bug in `serve` still answers the call
            _log.exception("serving %s failed", call.method)
            call.fail(RpcError.unanticipated(e))

    def _cancelled(self, ident: object) -> None:
        """Marks the call `session.cancel` names cancelled, where it is still being carried out."""
        if not _is_id(ident):
            return
        with self._lock:
            call = self._serving.get(ident)
        if call is not None:
            call.cancelled.set()

    def _answered(self, said: dict[str, Any]) -> None:
        """Takes a response, and settles the call it answers; one answering none is dropped."""
        ident = said["id"]
        if not isinstance(ident, int) or isinstance(ident, bool):
            return
        with self._lock:
            pending = self._pending.pop(ident, None)
        if pending is None:
            return
        error = said.get("error")
        if error is None:
            pending.set_result(said.get("result"))
            return
        told = cast("dict[str, Any]", error) if isinstance(error, dict) else {}
        code, message, data = told.get("code"), told.get("message"), told.get("data")
        pending.set_exception(
            RpcError(
                code if isinstance(code, int) else Code.INTERNAL_ERROR,
                message if isinstance(message, str) else "",
                cast("dict[str, Any]", data) if isinstance(data, dict) else None,
            )
        )
