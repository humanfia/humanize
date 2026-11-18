"""Each kind of pipe reads, writes and closes as a `Pipe` says, and `splice` joins two."""

from __future__ import annotations

import io
import os
import socket
import threading
from typing import TYPE_CHECKING, cast
from unittest import mock

import pytest
from websockets.exceptions import ConnectionClosedOK

from hmz.reach import (
    MESSAGE,
    SYNC,
    ProcessPipe,
    SocketPipe,
    StreamPipe,
    WebSocketPipe,
    splice,
    stdio,
)
from tests.unit.reach.memory import Memory

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path

    from hmz.rpc import Pipe


class Connection:
    """A WebSocket connection's messages, as `websockets.sync` hands them."""

    def __init__(self, *messages: str | bytes) -> None:
        self.messages = list(messages)
        self.sent: list[bytes] = []
        self.closed = False

    def recv(self) -> str | bytes:
        if not self.messages or self.closed:
            raise ConnectionClosedOK(None, None)
        return self.messages.pop(0)

    def send(self, message: bytes) -> None:
        if self.closed:
            raise ConnectionClosedOK(None, None)
        self.sent.append(message)

    def close(self) -> None:
        self.closed = True


def test_every_pipe_is_a_pipe_and_so_is_a_plain_socket() -> None:
    socket_pipe = SocketPipe(mock.Mock(spec=socket.socket), trusted=True)
    stream_pipe = StreamPipe(0, 1, trusted=True)
    websocket_pipe = WebSocketPipe(Connection())
    # Checked by the type checker as much as here: each is assignable to a `Pipe`.
    pipes: list[Pipe] = [
        socket_pipe,
        stream_pipe,
        websocket_pipe,
        Memory(),
        mock.Mock(spec=socket.socket),
    ]
    assert all(callable(getattr(one, "recv", None)) for one in pipes)
    plain: Pipe = socket.socket.__new__(socket.socket)
    assert callable(plain.sendall)
    assert [socket_pipe.trusted, stream_pipe.trusted, websocket_pipe.trusted] == [
        True,
        True,
        False,
    ]


def test_a_websocket_carries_bytes_across_its_binary_messages() -> None:
    pipe = WebSocketPipe(Connection(b"hel", b"", b"lo world"))
    assert pipe.recv(2) == b"he"
    assert pipe.recv(10) == b"l"
    assert pipe.recv(5) == b"lo wo"
    assert pipe.recv(10) == b"rld"
    assert pipe.recv(10) == b""


def test_a_text_message_closes_a_websocket() -> None:
    connection = Connection(b"one", "a text message", b"never read")
    pipe = WebSocketPipe(connection)
    assert pipe.recv(10) == b"one"
    assert pipe.recv(10) == b""
    assert connection.closed


def test_a_websocket_write_is_split_into_messages_the_relay_lets_through() -> None:
    connection = Connection()
    pipe = WebSocketPipe(connection)
    pipe.sendall(b"x" * (2 * MESSAGE + 1))
    assert [len(one) for one in connection.sent] == [MESSAGE, MESSAGE, 1]
    pipe.close()
    with pytest.raises(BrokenPipeError):
        pipe.sendall(b"after")


def test_a_socket_pipe_closes_once_and_then_stops_what_carried_it() -> None:
    sock = mock.Mock(spec=socket.socket)
    sock.recv.side_effect = OSError(9, "Bad file descriptor")
    ended = mock.Mock()
    pipe = SocketPipe(sock, trusted=False, ending=ended)
    pipe.close()
    pipe.close()
    sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    sock.close.assert_called_once_with()
    ended.assert_called_once_with()
    # A read the close woke is the end, not a failure.
    assert pipe.recv(10) == b""


def test_a_socket_pipe_failing_open_raises() -> None:
    sock = mock.Mock(spec=socket.socket)
    sock.recv.side_effect = ConnectionResetError("reset")
    with pytest.raises(ConnectionResetError):
        SocketPipe(sock, trusted=True).recv(10)


@pytest.fixture
def fds() -> tuple[int, int]:
    # Closed by the pipe, and not closed again here: a number closed may be another's by now.
    return os.pipe()


def test_a_stream_pipe_reads_and_writes_its_two_descriptors(
    fds: tuple[int, int],
) -> None:
    reading, writing = fds
    pipe = StreamPipe(reading, writing, trusted=True)
    pipe.sendall(b"round trip")
    assert pipe.recv(64) == b"round trip"
    pipe.close()
    pipe.close()
    assert pipe.recv(1) == b""


def test_stdio_is_this_process_s_own_streams_and_trusted() -> None:
    assert stdio().trusted


class Child:
    """A child as `subprocess.Popen` holds one, its streams in memory."""

    def __init__(self, stdout: int, *, code: int, said: bytes = b"") -> None:
        self.args = ["ssh", "box"]
        self.stdin = io.BytesIO()
        self.stdout = os.fdopen(stdout, "rb")
        self.stderr = io.BytesIO(said)
        self.returncode: int | None = None
        self.code = code
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = self.code
        return self.code

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


def test_a_child_that_ends_failing_raises_the_last_line_it_said() -> None:
    reading, writing = os.pipe()
    os.write(writing, SYNC + b"partial")
    os.close(writing)
    child = Child(
        reading, code=255, said=b"debug\nssh: Could not resolve hostname box\n"
    )
    pipe = ProcessPipe(cast("subprocess.Popen[bytes]", child), trusted=True)
    assert pipe.trusted
    assert pipe.recv(64) == b"partial"
    with pytest.raises(ConnectionError, match=r"^ssh: Could not resolve hostname box$"):
        pipe.recv(64)


def test_a_child_that_ended_failing_takes_no_more_saying_why() -> None:
    reading, writing = os.pipe()
    os.close(writing)
    child = Child(reading, code=1, said=b"hmz: the daemon cannot be reached: full\n")
    # Its standard input, which nothing reads any more.
    unread, written = os.pipe()
    os.close(unread)
    child.stdin = cast("io.BytesIO", os.fdopen(written, "wb"))
    pipe = ProcessPipe(cast("subprocess.Popen[bytes]", child), trusted=True)
    with pytest.raises(
        ConnectionError, match=r"^hmz: the daemon cannot be reached: full$"
    ):
        pipe.sendall(b"to it")
    pipe.close()


def test_a_child_that_ends_well_is_the_end_of_its_pipe() -> None:
    reading, writing = os.pipe()
    os.close(writing)
    child = Child(reading, code=0)
    pipe = ProcessPipe(cast("subprocess.Popen[bytes]", child), trusted=True)
    pipe.sendall(b"to it")
    assert child.stdin.getvalue() == b"to it"
    assert pipe.recv(64) == b""


def _saying(tmp_path: Path, said: bytes) -> ProcessPipe:
    """The pipe of a child that says this on its standard output, and ends well."""
    out = tmp_path / "out"
    out.write_bytes(said)
    child = Child(os.open(out, os.O_RDONLY), code=0)
    return ProcessPipe(cast("subprocess.Popen[bytes]", child), trusted=True)


def _all(pipe: ProcessPipe) -> bytes:
    read = b""
    while more := pipe.recv(5):
        read += more
    return read


def test_a_child_s_carrier_begins_after_the_first_sync_line(tmp_path: Path) -> None:
    """What a shell printed before `hmz` ran is no byte of it (Section 3.4.11 of wire.md)."""
    said = b"Welcome!\nlast login\n" + SYNC + b"\x00\x00\x00\x02{}" + SYNC
    assert _all(_saying(tmp_path, said)) == b"\x00\x00\x00\x02{}" + SYNC
    assert _all(_saying(tmp_path, b"x" * 65_524 + SYNC + b"frames")) == b"frames"


def test_a_child_that_says_64_kib_without_the_sync_line_fails(tmp_path: Path) -> None:
    pipe = _saying(tmp_path, b"x" * 65_525 + SYNC)
    with pytest.raises(ConnectionError, match=r"^No hmz-stdio/1 line came within"):
        pipe.recv(64)


def test_a_child_that_ends_before_the_sync_line_is_the_end_of_its_pipe(
    tmp_path: Path,
) -> None:
    assert _saying(tmp_path, b"hmz: not found\n").recv(64) == b""


def test_closing_a_child_s_pipe_stops_the_child() -> None:
    reading, writing = os.pipe()
    child = Child(reading, code=0)
    pipe = ProcessPipe(cast("subprocess.Popen[bytes]", child), trusted=True)
    pipe.close()
    os.close(writing)
    assert child.terminated
    assert child.stdin.closed
    with pytest.raises(BrokenPipeError):
        pipe.sendall(b"after")
    assert pipe.recv(1) == b""


def test_a_child_without_its_three_streams_is_refused() -> None:
    child = mock.Mock(stdin=None, stdout=None, stderr=None)
    with pytest.raises(ValueError, match="three"):
        ProcessPipe(child, trusted=True)


def test_a_splice_copies_each_way_and_closes_both_once_either_ends() -> None:
    near, far = Memory(trusted=True), Memory(trusted=True)
    near.feed(b"asked")
    far.feed(b"answered")
    done = threading.Thread(target=splice, args=(near, far))
    done.start()
    assert far.wrote(b"asked")
    assert near.wrote(b"answered")
    near.end()
    done.join(5)
    assert not done.is_alive()
    assert near.closed
    assert far.closed
