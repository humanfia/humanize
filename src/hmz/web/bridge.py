"""The page's bridges to daemons: `/rpc` to this machine's, `/dial` to another's.

Each is a WebSocket that carries bytes and nothing else: every binary message the page sends
goes to the daemon's end as bytes, and every byte from there goes back to the page in binary
messages, unchanged and in order; what the bytes are -- mutual TLS where `/dial` opened it,
frames and JSON-RPC inside -- is the page's and the daemon's (Sections 4.7 and 4.8 of web.md).
Over `/dial`, until the carrier is open, the page is told how it goes in text messages.

The WebSocket is spoken over the connection the HTTP server accepted, by `websockets`' protocol
without I/O of its own: `/rpc` and `/dial` are on the page's own port, beside its files.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
from typing import TYPE_CHECKING, Self

from websockets.datastructures import Headers
from websockets.exceptions import InvalidState
from websockets.frames import Frame, Opcode
from websockets.http11 import Request
from websockets.protocol import State
from websockets.server import ServerProtocol

from hmz.rpc.frames import LONGEST

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from http.server import BaseHTTPRequestHandler

    from hmz.rpc import Pipe

__all__ = ["WebSocket", "dials", "rpc"]

#: The most a reason a WebSocket is closed with may be, in bytes (Section 4.7.4 of web.md).
_REASON = 120

#: How much is read from either end at a time.
_CHUNK = 1 << 16

#: Normal closure, a policy refused, and a failure on the server's side (RFC 6455, 7.4.1).
_DONE, _POLICY, _FAILED = 1000, 1008, 1011

#: The route kinds `/dial` does not open: `/rpc` covers this machine's daemon, and a browser
#: opens `webrtc:` itself (Section 4.8.2 of web.md).
_UNDIALED = frozenset({"unix", "local", "webrtc"})


def _cut(reason: str) -> str:
    """A reason cut to what a close may carry, whole characters only."""
    return reason.encode()[:_REASON].decode(errors="ignore")


class WebSocket:
    """One WebSocket of the page, over the connection one request upgraded.

    Read on the thread that serves the request; written from any thread.
    """

    def __init__(
        self, handler: BaseHTTPRequestHandler, protocol: ServerProtocol
    ) -> None:
        self._handler = handler
        self._protocol = protocol
        self._lock = threading.Lock()

    @classmethod
    def accepted(
        cls, handler: BaseHTTPRequestHandler, headers: Mapping[str, str]
    ) -> Self | None:
        """Upgrades a request to a WebSocket, or answers why not and gives None.

        Args:
          handler: The request, its headers read.
          headers: What every answer carries beside its own.
        """
        # The request is read already: one protocol answers it, and one past it carries frames.
        handshake = ServerProtocol()
        request = Request(handler.path, Headers(handler.headers.items()))
        response = handshake.accept(request)
        for name, value in headers.items():
            response.headers[name] = value
        handshake.send_response(response)
        with contextlib.suppress(OSError):
            for data in handshake.data_to_send():
                handler.connection.sendall(data)
        if response.status_code != 101:  # noqa: PLR2004 -- Switching Protocols
            handler.close_connection = True
            return None
        opened = cls(handler, ServerProtocol(state=State.OPEN, max_size=LONGEST + 4))
        # A WebSocket may be quiet for as long as it likes (Section 4.3.5 of web.md).
        handler.connection.settimeout(None)
        return opened

    def messages(self) -> Iterator[bytes | str]:
        """Each message the page sends, a binary one in as many parts as it came in.

        Ends once the page closes the WebSocket, or the connection goes.
        """
        while True:
            try:
                read = self._handler.rfile.read1(_CHUNK)
            except OSError:
                read = b""
            with self._lock:
                if read:
                    self._protocol.receive_data(read)
                else:
                    self._protocol.receive_eof()
                frames = [
                    one
                    for one in self._protocol.events_received()
                    if isinstance(one, Frame)
                ]
            self._flush()
            text = False
            for frame in frames:
                if frame.opcode is Opcode.BINARY or (
                    frame.opcode is Opcode.CONT and not text
                ):
                    yield bytes(frame.data)
                elif frame.opcode is Opcode.TEXT:
                    text = True
                    yield bytes(frame.data).decode(errors="replace")
                elif frame.opcode is Opcode.CLOSE:
                    return
            if not read or self._protocol.close_expected():
                return

    def binary(self, data: bytes) -> None:
        """Sends bytes, as one binary message; nothing once it is closing."""
        with self._lock, contextlib.suppress(InvalidState):
            self._protocol.send_binary(data)
        self._flush()

    def text(self, said: str) -> None:
        """Sends one text message; nothing once it is closing."""
        with self._lock, contextlib.suppress(InvalidState):
            self._protocol.send_text(said.encode())
        self._flush()

    def close(self, code: int = _DONE, reason: str = "") -> None:
        """Closes it, saying why; nothing more is read or sent once it is closed."""
        with self._lock, contextlib.suppress(InvalidState):
            self._protocol.send_close(code, _cut(reason))
        self._flush()
        with contextlib.suppress(OSError):
            self._handler.connection.shutdown(socket.SHUT_RDWR)

    def _flush(self) -> None:
        with self._lock:
            for data in self._protocol.data_to_send():
                with contextlib.suppress(OSError):
                    self._handler.connection.sendall(data)


def _back(socket_: WebSocket, pipe: Pipe) -> None:
    """Carries every byte from a daemon's end back to the page, on a thread of its own.

    The WebSocket is closed once that end closes.
    """

    def carries() -> None:
        while True:
            try:
                read = pipe.recv(_CHUNK)
            except OSError:
                read = b""
            if not read:
                socket_.close(_DONE, "The daemon closed.")
                return
            socket_.binary(read)

    threading.Thread(target=carries, daemon=True, name="hmz-web-back").start()


def _forth(socket_: WebSocket, pipe: Callable[[], Pipe | None]) -> None:
    """Carries every binary message of the page to a daemon's end, until either closes.

    A text message closes both (Sections 4.7.2 and 4.8.5 of web.md), as does a binary one
    before the end is open.
    """
    for said in socket_.messages():
        held = pipe()
        if isinstance(said, str) or held is None:
            return
        try:
            held.sendall(said)
        except OSError:
            return


def rpc(socket_: WebSocket) -> None:
    """`/rpc`: the WebSocket carried to the socket of this machine's daemon (Section 4.7 of web.md).

    The daemon is started where none runs.
    """
    from hmz import daemon
    from hmz.reach import dial

    try:
        pipe = dial("unix:", start=daemon.start)
    except (OSError, ValueError) as why:
        socket_.close(_FAILED, f"The daemon cannot be reached: {why}")
        return
    _back(socket_, pipe)
    try:
        _forth(socket_, lambda: pipe)
    finally:
        with contextlib.suppress(OSError):
            pipe.close()
        socket_.close(_DONE)


def dials(socket_: WebSocket, route: str, pinned: str) -> None:
    """`/dial`: the WebSocket carried to the daemon a route reaches (Section 4.8 of web.md).

    Opened as this machine's device, the page told how opening it goes until it is open.
    """
    from hmz.reach import Route
    from hmz.runtime.doing.daemons import Dialing

    try:
        parsed = Route.parse(route)
    except ValueError:
        socket_.close(_POLICY, f"{route or 'That'} is not a route.")
        return
    if parsed.kind in _UNDIALED:
        socket_.close(_POLICY, f"{route} is not dialed here.")
        return
    if not parsed.trusted and not pinned:
        socket_.close(_POLICY, f"{route} needs the id of the daemon it reaches.")
        return

    def told(state: str, detail: str) -> None:
        socket_.text(json.dumps({"state": state, "detail": detail}))

    dialing = Dialing(parsed, pinned, told)
    opened: list[Pipe] = []

    def opens() -> None:
        try:
            pipe, note = dialing.opens()
        except Exception as why:  # noqa: BLE001 -- whatever it was is what the page is told
            said = str(why) or type(why).__name__
            told("failed", said)
            socket_.close(_FAILED, said)
            return
        opened.append(pipe)
        told("up", note)
        _back(socket_, pipe)

    threading.Thread(target=opens, daemon=True, name="hmz-web-dial").start()
    try:
        _forth(socket_, lambda: opened[0] if opened else None)
    finally:
        # However it ended, what was started for it is stopped (Section 4.8.6 of web.md).
        for pipe in opened:
            with contextlib.suppress(OSError):
                pipe.close()
        dialing.close()
        socket_.close(_DONE)
