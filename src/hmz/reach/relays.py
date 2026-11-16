"""Both of a native peer's sides of the relay: a client joining, and a daemon registered.

The relay joins a client to a daemon that cannot reach each other, and is trusted by neither:
it splices the bytes of a native join and reads none of them, since what it splices is TLS end
to end (Section 5 of the wire protocol). Each side opens a WebSocket to it, says what it is in
a text message or two, and from then on its binary messages are the carrier. Only these first
messages are this module's: :func:`join` is the client's, and :class:`RelayListener` the
daemon's, which keeps a control connection registered under its daemon id and opens a
WebSocket of its own for each client that joins. The relay itself is `hmz relay serve`'s.
"""

from __future__ import annotations

import contextlib
import json
import logging
import queue
import threading
import time
from typing import TYPE_CHECKING, Any, cast

from hmz.reach.dialing import OPENING, websocket
from hmz.reach.pipes import WebSocketPipe
from hmz.reach.racing import Backoff

if TYPE_CHECKING:
    from collections.abc import Callable

    from websockets.sync.client import ClientConnection

    from hmz.rpc.pipe import Pipe

__all__ = ["RelayListener", "join"]

log = logging.getLogger(__name__)


def join(url: str, daemon: str, timeout: float = OPENING) -> WebSocketPipe:
    """Joins the daemon registered at a relay under an id, natively (Section 5.5).

    Args:
      url: The relay's WebSocket URL.
      daemon: The daemon id to join.
      timeout: How long joining may take, opening the WebSocket included.

    Returns:
      The splice, untrusted: whoever answers it is proven only by the TLS put over it.

    Raises:
      TimeoutError: If the relay did not answer within `timeout`.
      OSError: If the relay could not be reached or refused the join, with what it said why.
    """
    from websockets.exceptions import ConnectionClosed

    ending = time.monotonic() + timeout
    connection = websocket(url, timeout)
    try:
        connection.send(json.dumps({"t": "join", "id": daemon, "kind": "native"}))
        said = _read(connection.recv(max(ending - time.monotonic(), 0.0)))
    except TimeoutError:
        connection.close()
        raise
    except ConnectionClosed as why:
        connection.close()
        raise ConnectionError(f"The relay at {url} did not join: {why}") from why
    if said.get("t") == "joined":
        return WebSocketPipe(connection)
    connection.close()
    why = said.get("why") if said.get("t") == "error" else None
    raise ConnectionError(
        why if isinstance(why, str) else f"The relay at {url} answered no join."
    )


class RelayListener:
    """A daemon's registration at a relay, and the clients that join it there natively.

    Registered as long as it is open: a control connection that drops, or a relay that cannot
    be reached, is tried again as Section 3.6.4 says, after 1 second and doubling to 60, and
    never stops the daemon serving anything else. A WebRTC join, and every signal, is
    `hmz.rtc`'s, and is let pass.
    """

    def __init__(
        self, url: str, daemon: str, prove: Callable[[str], tuple[str, str]]
    ) -> None:
        """Starts registering.

        Args:
          url: The relay's WebSocket URL.
          daemon: This daemon's id.
          prove: What answers the relay's challenge with its nonce: the daemon's device
            certificate in base64 of its DER, and the base64url of its 64-byte signature over
            `hmz-relay/1`, a line feed and the nonce (Section 5.4.2).
        """
        self.url = url
        self._daemon = daemon
        self._prove = prove
        self._joined: queue.Queue[Pipe | None] = queue.Queue()
        self._closed = threading.Event()
        self._holding = threading.Lock()
        self._control: ClientConnection | None = None
        #: What went wrong last, "" while registered.
        self.said = ""
        #: Set while registered, and cleared while not.
        self.registered = threading.Event()
        threading.Thread(target=self._keeps, daemon=True, name="hmz-relay").start()

    def accept(self) -> Pipe:
        """The next client joined, waiting for one.

        Raises:
          OSError: Once it is closed.
        """
        joined = self._joined.get()
        if joined is None:
            self._joined.put(None)
            raise OSError(f"the registration at {self.url} is closed")
        return joined

    def close(self) -> None:
        """Stops registering, and closes every client joined but not yet accepted."""
        with self._holding:
            self._closed.set()
            control = self._control
            left: list[Pipe] = []
            while True:
                try:
                    one = self._joined.get_nowait()
                except queue.Empty:
                    break
                if one is not None:
                    left.append(one)
            self._joined.put(None)
        if control is not None:
            control.close()
        for one in left:
            one.close()

    def _keeps(self) -> None:
        """Keeps one control connection registered until it is closed."""
        from websockets.exceptions import ConnectionClosed

        backoff = Backoff()
        while not self._closed.is_set():
            try:
                control = websocket(self.url)
            except OSError as why:
                self._failed(f"The relay at {self.url} could not be reached: {why}")
                self._closed.wait(backoff.next())
                continue
            with self._holding:
                self._control = control
            if self._closed.is_set():
                control.close()
                return
            try:
                self._registers(control)
                backoff.reset()
                self.said = ""
                self.registered.set()
                self._serves(control)
            except (ConnectionClosed, OSError) as why:
                self._failed(str(why) or f"The relay at {self.url} closed.")
            except Exception as why:  # noqa: BLE001 -- a proof not made, a relay misspoken
                # Whatever it is, the registration is tried again rather than given up on.
                self._failed(f"The registration at {self.url} failed: {why!r}")
            finally:
                self.registered.clear()
                control.close()
            self._closed.wait(backoff.next())

    def _failed(self, why: str) -> None:
        if not self._closed.is_set():
            self.said = why
            log.warning("%s", why)

    def _registers(self, control: ClientConnection) -> None:
        """Registers this daemon's id over a control connection (Section 5.4).

        Raises:
          ConnectionError: Saying why the relay would not have it.
        """
        control.send(json.dumps({"t": "register", "id": self._daemon}))
        challenge = _read(control.recv(OPENING))
        nonce = challenge.get("nonce")
        if challenge.get("t") != "challenge" or not isinstance(nonce, str):
            raise ConnectionError(_why(challenge, self.url))
        cert, sig = self._prove(nonce)
        control.send(json.dumps({"t": "prove", "cert": cert, "sig": sig}))
        answer = _read(control.recv(OPENING))
        if answer.get("t") != "registered":
            raise ConnectionError(_why(answer, self.url))

    def _serves(self, control: ClientConnection) -> None:
        """Answers each native join told over the control connection, until it ends.

        Raises:
          ConnectionError: When the relay says an error, which ends the connection.
        """
        while True:
            told = _read(control.recv())
            if told.get("t") == "error":
                raise ConnectionError(_why(told, self.url))
            conn = told.get("conn")
            if (
                told.get("t") == "join"
                and told.get("kind") == "native"
                and isinstance(conn, str)
            ):
                threading.Thread(
                    target=self._accepts,
                    args=(control, conn),
                    daemon=True,
                    name="hmz-relay",
                ).start()

    def _accepts(self, control: ClientConnection, conn: str) -> None:
        """Opens the WebSocket that one join is spliced to, or refuses it saying why."""
        from websockets.exceptions import ConnectionClosed

        try:
            joined = websocket(self.url)
        except OSError as why:
            with contextlib.suppress(Exception):
                control.send(json.dumps({"t": "refuse", "conn": conn, "why": str(why)}))
            return
        try:
            joined.send(json.dumps({"t": "accept", "conn": conn}))
        except ConnectionClosed:
            return
        # Under the lock close() drains under, so that nothing is queued after it has.
        with self._holding:
            if not self._closed.is_set():
                self._joined.put(WebSocketPipe(joined))
                return
        joined.close()


def _read(message: str | bytes) -> dict[str, Any]:
    """A control message, or nothing at all for one that is not a JSON object in text."""
    if not isinstance(message, str):
        return {}
    try:
        held: object = json.loads(message)
    except ValueError:
        return {}
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}


def _why(said: dict[str, Any], url: str) -> str:
    """Why the relay said what it did instead of what was asked."""
    why = said.get("why")
    return why if isinstance(why, str) else f"The relay at {url} answered out of turn."
