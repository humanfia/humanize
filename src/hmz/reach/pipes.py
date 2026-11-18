"""A carrier as this side holds it: a pipe of bytes each way, shaped like a socket.

Every carrier comes to the same thing once it is open -- a socket, the standard streams of a
child, a WebSocket whose binary messages carry the bytes -- and what is put over it next, TLS
or the frames themselves, should not have to know which it was. :class:`hmz.rpc.Pipe` is that
one shape, of a socket's `recv`, `sendall` and `close`, and this module is a pipe of each kind
there is. Whether a carrier is trusted is its route's to say
(:attr:`hmz.reach.Route.trusted`), and each pipe here also says it as `trusted`.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import threading
from typing import IO, TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.rpc.pipe import Pipe

__all__ = [
    "MESSAGE",
    "SYNC",
    "Messages",
    "ProcessPipe",
    "SocketPipe",
    "StreamPipe",
    "WebSocketPipe",
    "splice",
    "stdio",
]

#: The most one WebSocket message carries: what the relay lets through (Section 5.6.1).
MESSAGE = 1 << 20

#: What `hmz daemon connect --stdio` writes before the daemon's first byte, and what the carrier
#: of a `stdio:` route begins after (Section 3.4.11 of wire.md).
SYNC = b"hmz-stdio/1\n"

#: How many bytes may come before :data:`SYNC` hold it.
_SYNCING = 1 << 16

#: How much one read of a splice asks for.
_CHUNK = 1 << 16

#: How long a child is given to stop before it is killed.
_STOPPING = 5.0


class SocketPipe:
    """A connected stream socket: a Unix socket, or TCP however it was reached."""

    def __init__(
        self,
        sock: socket.socket,
        *,
        trusted: bool,
        ending: Callable[[], object] | None = None,
    ) -> None:
        """Holds a socket.

        Args:
          sock: It, connected and blocking.
          trusted: Whether its carrier is trusted.
          ending: What is done once it is closed: stopping the EasyTier that carries it.
        """
        self._sock = sock
        self._trusted = trusted
        self._ending = ending
        self._closing = threading.Lock()
        self._closed = False

    @property
    def trusted(self) -> bool:
        return self._trusted

    def recv(self, size: int) -> bytes:
        try:
            return self._sock.recv(size)
        except OSError:
            if self._closed:
                return b""
            raise

    def sendall(self, data: bytes) -> None:
        self._sock.sendall(data)

    def close(self) -> None:
        with self._closing:
            if self._closed:
                return
            self._closed = True
        # Shut down before it is closed, which is what wakes a read waiting on it.
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        if self._ending is not None:
            self._ending()


class StreamPipe:
    """Two file descriptors, one read and one written: this process's own standard streams."""

    def __init__(self, reading: int, writing: int, *, trusted: bool) -> None:
        """Holds the two.

        Args:
          reading: What is read.
          writing: What is written.
          trusted: Whether its carrier is trusted.
        """
        self._reading = reading
        self._writing = writing
        self._trusted = trusted
        self._closing = threading.Lock()
        self._closed = False

    @property
    def trusted(self) -> bool:
        return self._trusted

    def recv(self, size: int) -> bytes:
        try:
            return os.read(self._reading, size)
        except OSError:
            if self._closed:
                return b""
            raise

    def sendall(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(self._writing, view) :]

    def close(self) -> None:
        with self._closing:
            if self._closed:
                return
            self._closed = True
        for one in {self._reading, self._writing}:
            with contextlib.suppress(OSError):
                os.close(one)


class ProcessPipe:
    """The standard input and output of a child: `hmz daemon connect --stdio`, wherever it runs.

    What the child says on its standard error is kept, and its last line is what a carrier
    that ended badly raises: `ssh` saying why it could not reach the host. What it says on its
    standard output up to and including :data:`SYNC` is no byte of the carrier: what a shell
    that `ssh` or WSL starts there prints before `hmz` runs.
    """

    def __init__(self, process: subprocess.Popen[bytes], *, trusted: bool) -> None:
        """Holds a child.

        Args:
          process: It, started with a pipe for each of its three streams.
          trusted: Whether its carrier is trusted.

        Raises:
          ValueError: If it was started without them.
        """
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise ValueError(
                "a child carries a pipe only with all three of its streams"
            )
        self._process = process
        self._stdin = process.stdin
        self._stdout = process.stdout
        self._stderr = process.stderr
        self._trusted = trusted
        self._closing = threading.Lock()
        self._closed = False
        self._said = ""
        self._synced = False
        self._held = b""
        self._heard = threading.Thread(
            target=self._hears, args=(process.stderr,), daemon=True, name="hmz-reach"
        )
        self._heard.start()

    @property
    def trusted(self) -> bool:
        return self._trusted

    def recv(self, size: int) -> bytes:
        while not self._synced:
            read = self._read(_CHUNK)
            if not read:
                return read
            self._held += read
            at = self._held.find(SYNC, 0, _SYNCING)
            if at >= 0:
                self._held = self._held[at + len(SYNC) :]
                self._synced = True
            elif len(self._held) >= _SYNCING:
                msg = f"No {SYNC.decode().strip()} line came within the first {_SYNCING} bytes."
                raise ConnectionError(msg)
        if self._held:
            read, self._held = self._held[:size], self._held[size:]
            return read
        return self._read(size)

    def _read(self, size: int) -> bytes:
        """One read of the child's standard output, raising why it failed once it has ended."""
        try:
            read = os.read(self._stdout.fileno(), size)
        except (OSError, ValueError):
            if self._closed:
                return b""
            raise
        if read or self._closed:
            return read
        # The end of its output: a child that failed says why on its way out.
        self._ended()
        return b""

    def _ended(self) -> None:
        """Raises why the child failed, where it has ended and failed."""
        try:
            code = self._process.wait(_STOPPING)
        except subprocess.TimeoutExpired:
            return
        self._heard.join(_STOPPING)
        if code and not self._closed:
            argv = self._process.args
            named = argv[0] if isinstance(argv, list | tuple) else argv
            raise ConnectionError(self._said or f"{named!s} exited {code}.")

    def sendall(self, data: bytes) -> None:
        try:
            self._stdin.write(data)
            self._stdin.flush()
        except ValueError as closed:
            raise BrokenPipeError(str(closed)) from closed
        except BrokenPipeError:
            # It takes no more: a child that failed says why, as where its output ends.
            self._ended()
            raise

    def close(self) -> None:
        with self._closing:
            if self._closed:
                return
            self._closed = True
        with contextlib.suppress(OSError, ValueError):
            self._stdin.close()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(_STOPPING)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        for stream in (self._stdout, self._stderr):
            with contextlib.suppress(OSError, ValueError):
                stream.close()

    def _hears(self, stderr: IO[bytes]) -> None:
        """Keeps the last line the child says on its standard error, until it says no more."""
        with contextlib.suppress(OSError, ValueError):
            for line in stderr:
                said = line.decode(errors="replace").strip()
                if said:
                    self._said = said


class Messages(Protocol):
    """What of a WebSocket connection a pipe uses: that of `websockets.sync`, either side."""

    def recv(self) -> str | bytes: ...
    def send(self, message: bytes) -> None: ...
    def close(self) -> None: ...


class WebSocketPipe:
    """A WebSocket whose binary messages carry the bytes (Section 3.4.6), and the relay's splice.

    A text message closes it, as Section 3.4.6 says, and is read as its end.
    """

    def __init__(self, connection: Messages, *, trusted: bool = False) -> None:
        """Holds a connection.

        Args:
          connection: It, open, with nothing more of a handshake to come over it.
          trusted: Whether its carrier is trusted, which no WebSocket is (Section 3.5.2).
        """
        self._connection = connection
        self._trusted = trusted
        self._held = b""

    @property
    def trusted(self) -> bool:
        return self._trusted

    def recv(self, size: int) -> bytes:
        from websockets.exceptions import ConnectionClosed

        while not self._held:
            try:
                message = self._connection.recv()
            except ConnectionClosed:
                return b""
            if isinstance(message, str):
                self.close()
                return b""
            self._held = message
        read, self._held = self._held[:size], self._held[size:]
        return read

    def sendall(self, data: bytes) -> None:
        from websockets.exceptions import ConnectionClosed

        try:
            for at in range(0, len(data), MESSAGE):
                self._connection.send(data[at : at + MESSAGE])
        except ConnectionClosed as closed:
            raise BrokenPipeError(str(closed)) from closed

    def close(self) -> None:
        self._connection.close()


def stdio() -> StreamPipe:
    """This process's standard input and output, as the trusted pipe `connect --stdio` holds."""
    return StreamPipe(0, 1, trusted=True)


def splice(one: Pipe, other: Pipe) -> None:
    """Copies each pipe's bytes to the other until either ends, then closes both.

    Which is the whole of `hmz daemon connect --stdio`: its standard streams spliced to the
    socket of the daemon of its machine. It returns once either way has ended rather than once
    both have: a read of a pipe that is a file descriptor is not woken by its closing, and this
    process's standard input may say nothing more for as long as it is open.

    Args:
      one: A pipe.
      other: Another.
    """
    ended = threading.Event()

    def copies(source: Pipe, sink: Pipe) -> None:
        try:
            while read := source.recv(_CHUNK):
                sink.sendall(read)
        except OSError:
            pass
        finally:
            ended.set()

    for source, sink in ((one, other), (other, one)):
        threading.Thread(
            target=copies, args=(source, sink), daemon=True, name="hmz-reach"
        ).start()
    ended.wait()
    one.close()
    other.close()
