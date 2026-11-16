"""One session of `protocol/wire.md` with one daemon, as a program of the SDK holds it.

What every epic a program makes is run through (Section 4.21 of python.md): calls of the
OpenRPC document answered on the thread that made them, a refusal raised as
:class:`hmz.runtime.Refused` with the daemon's code and data, and every notification of the
session handed, in order, to one listener on a thread of the client's own.
"""

from __future__ import annotations

import contextlib
import queue
import threading
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from types import TracebackType

    from hmz.rpc import Call, Peer

__all__ = ["Client"]

#: Why a call on a session that has ended is refused, and with what code.
WENT = "the daemon went away"
_GONE = 503

#: What a notification waits as until a listener takes it.
type _Told = tuple[str, dict[str, Any]] | None


class Client:
    """One session with one daemon; a context manager, closed to end it."""

    def __init__(
        self, dial: Callable[[Callable[[Call], None]], tuple[Peer, dict[str, Any]]]
    ) -> None:
        """Opens the session and says hello.

        Made by :meth:`local`, or by whatever else reaches a daemon over a pipe of its own.

        Args:
          dial: What opens the session, handing every call the daemon sends to the callable
            it is given, and answers its end and what `session.hello` answered.

        Raises:
          OSError: As `dial` raises it.
        """
        self._inbox: queue.SimpleQueue[_Told] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._listening = False
        self._closed = False
        self._peer, said = dial(self._told)
        self.daemon_id = str(said.get("daemon_id") or "")
        self.version = str(said.get("version") or "")
        self.protocol = str(said.get("protocol") or "")
        self.capabilities: tuple[str, ...] = tuple(said.get("capabilities") or ())
        self.device = str(said.get("device") or "")
        threading.Thread(target=self._ends, daemon=True, name="hmz-client-ends").start()

    @classmethod
    def local(cls, *, name: str = "", kind: str = "sdk") -> Client:
        """A session with this machine's daemon over `unix:`, started where none runs.

        Args:
          name: What this client is called, "" for nothing.
          kind: What it is: `sdk`, `cli`, `tui`.

        Raises:
          OSError: If the daemon cannot be reached or started, or speaks another protocol.
        """
        from hmz import daemon
        from hmz.daemon import where
        from hmz.daemon.link import dialed

        daemon.start()
        return cls(lambda serve: dialed(where.at(), name, kind, serve=serve))

    def _told(self, call: Call) -> None:
        if call.id is None:
            self._inbox.put((call.method, call.params))

    def _ends(self) -> None:
        self._peer.wait()
        self._inbox.put(None)

    @property
    def closed(self) -> bool:
        """Whether the session has ended."""
        return self._peer.closed

    def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        idem: str | None = None,
        seconds: float | None = None,
    ) -> Any:
        """Makes one call, and waits for its result.

        Args:
          method: The method, as the OpenRPC document names it.
          params: Its parameters by name.
          idem: The write's idempotency key, added to `params` where given.
          seconds: How long to wait, or None for as long as it takes.

        Raises:
          Refused: With the error's message, code and data where the daemon answers one, and
            503 once the session has ended.
          TimeoutError: If no answer came in time.
        """
        from hmz.rpc import Closed, RpcError
        from hmz.runtime import Refused

        said = dict(params or {})
        if idem is not None:
            said["idem"] = idem
        try:
            pending = self._peer.request(method, said)
        except (Closed, OSError):
            raise Refused(WENT, code=_GONE) from None
        try:
            return pending.result(seconds)
        except RpcError as why:
            raise Refused(why.message, code=why.code, data=why.data or {}) from None
        except Closed:
            raise Refused(WENT, code=_GONE) from None
        except TimeoutError:
            with contextlib.suppress(Closed, OSError):
                pending.cancel()
            raise TimeoutError(f"no answer to {method!r} in {seconds}s") from None

    def heard(self, listener: Callable[[str, dict[str, Any]], None]) -> None:
        """Hands every notification, those already waiting first, to `listener`, in order.

        Args:
          listener: What is handed each method and its parameters, on a thread of the
            client's own; what it raises is let go.

        Raises:
          RuntimeError: If the client already has one.
        """
        with self._lock:
            if self._listening:
                raise RuntimeError("this client already has a listener")
            self._listening = True

        def pumps() -> None:
            while (told := self._inbox.get()) is not None:
                with contextlib.suppress(Exception):
                    listener(*told)

        threading.Thread(target=pumps, daemon=True, name="hmz-client").start()

    def close(self) -> None:
        """Ends the session, and every subscription of it; every epic goes on."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._peer.close()

    def __enter__(self) -> Self:
        """Holds the session for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Ends the session, however the block ended."""
        self.close()
