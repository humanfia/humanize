"""The client half of the protocol, against a peer that answers from a script."""

from __future__ import annotations

import errno
import io
import queue
import threading
from typing import TYPE_CHECKING, Any, BinaryIO, cast

import pytest

from hmz.coganchor.proto import (
    CHUNK_SIZE,
    PROTOCOL_VERSION,
    Channel,
    Frame,
    Kind,
    Op,
    ProtocolError,
    RemoteOSError,
    Stream,
)
from hmz.coganchor.remote import RemoteClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


class Peer(Channel):
    """A channel whose far end is `answer`, called with every frame the client sends."""

    def __init__(self, answer: Callable[[Frame], list[Frame]]) -> None:
        self.answer = answer
        self.sent: list[Frame] = []
        self.inbox: queue.SimpleQueue[Frame | ProtocolError | None] = (
            queue.SimpleQueue()
        )
        self.shut = False

    def send(self, frame: Frame) -> None:
        if self.shut:
            raise ProtocolError("channel is closed")
        self.sent.append(frame)
        for one in self.answer(frame):
            self.inbox.put(one)

    def recv(self) -> Frame | None:
        got = self.inbox.get()
        if isinstance(got, ProtocolError):
            raise got
        return got

    def close(self) -> None:
        self.shut = True
        self.inbox.put(None)


def hello(frame: Frame, version: int = PROTOCOL_VERSION) -> list[Frame]:
    if frame.op is Op.HELLO:
        return [Frame.reply(frame.msg_id, version=version, hostname="far")]
    return []


def silent(frame: Frame) -> list[Frame]:
    return []


def ignore(*_: object) -> None:
    """Takes a callback's arguments and does nothing with them."""


class Opener:
    """Opens clients past their handshake, to a peer answering everything else with `answer`."""

    def __init__(self) -> None:
        self.held: list[RemoteClient] = []

    def __call__(
        self, answer: Callable[[Frame], list[Frame]]
    ) -> tuple[RemoteClient, Peer]:
        def both(frame: Frame) -> list[Frame]:
            return hello(frame) if frame.op is Op.HELLO else answer(frame)

        peer = Peer(both)
        client = RemoteClient(peer, timeout=5.0)
        client.start("secret")
        self.held.append(client)
        return client, peer


@pytest.fixture
def opened() -> Iterator[Opener]:
    opener = Opener()
    yield opener
    for one in opener.held:
        one.close()


def test_the_handshake_says_the_version_and_the_token() -> None:
    peer = Peer(hello)
    client = RemoteClient(peer)
    info = client.start("secret")
    client.close()
    assert info["hostname"] == "far"
    assert client.info == info
    assert peer.sent[0].op is Op.HELLO
    assert peer.sent[0].meta["version"] == PROTOCOL_VERSION
    assert peer.sent[0].meta["token"] == "secret"


def test_a_target_speaking_another_version_is_refused() -> None:
    client = RemoteClient(Peer(lambda frame: hello(frame, version=99)))
    with pytest.raises(ProtocolError, match="protocol 99"):
        client.start()
    client.close()


def test_a_client_never_started_closes_quietly() -> None:
    peer = Peer(hello)
    client = RemoteClient(peer)
    client.close()
    assert peer.shut


HELPERS: list[tuple[Callable[[RemoteClient], object], Op, dict[str, Any]]] = [
    (lambda c: c.listdir("/w"), Op.LISTDIR, {"path": "/w"}),
    (
        lambda c: c.mkdir("/w/d"),
        Op.MKDIR,
        {"path": "/w/d", "mode": 0o777, "parents": False},
    ),
    (
        lambda c: c.mkdir("/w/d", 0o700, parents=True),
        Op.MKDIR,
        {"path": "/w/d", "mode": 0o700, "parents": True},
    ),
    (lambda c: c.rmdir("/w/d"), Op.RMDIR, {"path": "/w/d"}),
    (lambda c: c.unlink("/w/f"), Op.UNLINK, {"path": "/w/f"}),
    (
        lambda c: c.rename("/a", "/b"),
        Op.RENAME,
        {"src": "/a", "dst": "/b", "replace": True},
    ),
    (
        lambda c: c.rename("/a", "/b", replace=False),
        Op.RENAME,
        {"src": "/a", "dst": "/b", "replace": False},
    ),
    (lambda c: c.symlink("t", "/l"), Op.SYMLINK, {"target": "t", "path": "/l"}),
    (lambda c: c.link("/a", "/b"), Op.LINK, {"src": "/a", "dst": "/b"}),
    (lambda c: c.chmod("/f", 0o600), Op.CHMOD, {"path": "/f", "mode": 0o600}),
    (
        lambda c: c.utime("/f", 1, None),
        Op.UTIME,
        {"path": "/f", "atime_ns": 1, "mtime_ns": None},
    ),
    (lambda c: c.call(Op.STAT, path="/f"), Op.STAT, {"path": "/f"}),
]


@pytest.mark.parametrize(("call", "op", "meta"), HELPERS)
def test_each_helper_asks_for_its_operation(
    opened: Opener,
    call: Callable[[RemoteClient], object],
    op: Op,
    meta: dict[str, Any],
) -> None:
    client, peer = opened(lambda frame: [Frame.reply(frame.msg_id, ok=True)])
    call(client)
    asked = peer.sent[-1]
    assert asked.op is op
    assert {key: asked.meta[key] for key in meta} == meta


def test_a_reply_is_handed_back(
    opened: Opener,
) -> None:
    client, _ = opened(
        lambda frame: [Frame.reply(frame.msg_id, entries=[{"name": "a"}])]
    )
    assert client.listdir("/w") == {"entries": [{"name": "a"}]}


def test_an_error_is_raised_with_the_targets_errno(
    opened: Opener,
) -> None:
    client, _ = opened(
        lambda frame: [
            Frame.error(frame.msg_id, FileNotFoundError(errno.ENOENT, "gone", "/x"))
        ]
    )
    with pytest.raises(RemoteOSError) as raised:
        client.unlink("/x")
    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == "/x"


def test_a_target_that_never_answers_times_out() -> None:
    client = RemoteClient(Peer(silent), timeout=0.01)
    with pytest.raises(TimeoutError) as raised:
        client.rmdir("/d")
    assert raised.value.errno == errno.ETIMEDOUT


def test_a_file_is_read_chunk_by_chunk(
    opened: Opener,
) -> None:
    def reading(frame: Frame) -> list[Frame]:
        return [
            Frame.chunk(frame.msg_id, Stream.DATA, b"hello "),
            Frame.chunk(frame.msg_id, Stream.DATA, b"world"),
            Frame.end(frame.msg_id),
            Frame.reply(frame.msg_id, size=11),
        ]

    client, peer = opened(reading)
    sink = io.BytesIO()
    assert client.read_file("/w/f", sink) == {"size": 11}
    assert sink.getvalue() == b"hello world"
    assert peer.sent[-1].meta["path"] == "/w/f"


def test_a_file_is_written_in_chunks_then_ended(
    opened: Opener,
) -> None:
    def writing(frame: Frame) -> list[Frame]:
        return [Frame.reply(frame.msg_id, size=5)] if frame.kind is Kind.END else []

    client, peer = opened(writing)
    body = b"x" * (CHUNK_SIZE + 5)
    assert client.write_file("/w/f", io.BytesIO(body), 0o644) == {"size": 5}
    request, *chunks, end = peer.sent[1:]
    assert request.op is Op.WRITE
    assert request.meta["mode"] == 0o644
    assert b"".join(one.body for one in chunks) == body
    assert all(one.kind is Kind.CHUNK for one in chunks)
    assert end.kind is Kind.END


class Unreadable(io.RawIOBase):
    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        raise OSError(errno.EIO, "disk")


def test_a_write_whose_source_fails_raises_and_is_forgotten(
    opened: Opener,
) -> None:
    client, _ = opened(silent)
    with pytest.raises(OSError, match="disk"):
        client.write_file("/w/f", cast("BinaryIO", Unreadable()))


def test_a_command_streams_its_output_and_its_exit(
    opened: Opener,
) -> None:
    def running(frame: Frame) -> list[Frame]:
        if frame.op is Op.EXEC:
            return [
                Frame.chunk(frame.msg_id, Stream.STDOUT, b"out"),
                Frame.chunk(frame.msg_id, Stream.STDERR, b"err"),
                Frame.reply(frame.msg_id, exit_code=3),
            ]
        if frame.op is Op.SIGNAL:
            return [Frame.reply(frame.msg_id)]
        return []

    client, peer = opened(running)
    output: list[tuple[Stream, bytes]] = []
    finished = threading.Event()
    ended: list[tuple[dict[str, Any] | None, OSError | None]] = []

    def on_exit(result: dict[str, Any] | None, error: OSError | None) -> None:
        ended.append((result, error))
        finished.set()

    handle = client.start_exec(
        ["ls", "-l"],
        "/w",
        {"A": "b"},
        lambda stream, data: output.append((stream, data)),
        on_exit,
        program="/bin/ls",
        tty=True,
        winsize=(24, 80),
        fence={"online": False},
    )
    assert finished.wait(5)
    assert output == [(Stream.STDOUT, b"out"), (Stream.STDERR, b"err")]
    assert ended == [({"exit_code": 3}, None)]
    asked = peer.sent[1]
    for key, value in {
        "argv": ["ls", "-l"],
        "cwd": "/w",
        "env": {"A": "b"},
        "program": "/bin/ls",
        "tty": True,
        "winsize": [24, 80],
        "fence": {"online": False},
    }.items():
        assert asked.meta[key] == value

    handle.send_stdin(b"in")
    handle.close_stdin()
    handle.signal(2)
    stdin, closed, signalled = peer.sent[2:5]
    assert (stdin.kind, stdin.stream, stdin.body) == (Kind.CHUNK, Stream.STDIN, b"in")
    assert (closed.kind, closed.stream) == (Kind.END, Stream.STDIN)
    assert signalled.op is Op.SIGNAL
    assert signalled.meta["target"] == handle.msg_id
    assert signalled.meta["sig"] == 2


def test_a_signal_the_target_cannot_take_is_let_go(
    opened: Opener,
) -> None:
    client, peer = opened(
        lambda frame: (
            [Frame.error(frame.msg_id, OSError(errno.ESRCH, "gone"))]
            if frame.op is Op.SIGNAL
            else []
        )
    )
    handle = client.start_exec(["x"], "/", {}, ignore, ignore)
    handle.signal(15)
    assert peer.sent[-1].op is Op.SIGNAL
    assert peer.sent[-1].meta["sig"] == 15


def test_a_tunnel_carries_bytes_both_ways(
    opened: Opener,
) -> None:
    def tunnelling(frame: Frame) -> list[Frame]:
        if frame.kind is Kind.CHUNK:
            return [Frame.chunk(frame.msg_id, Stream.DATA, frame.body.upper())]
        if frame.kind is Kind.END:
            return [Frame.reply(frame.msg_id)]
        return []

    client, peer = opened(tunnelling)
    heard: list[bytes] = []
    closed = threading.Event()

    def on_close(*_: object) -> None:
        closed.set()

    handle = client.open_tunnel(
        "example.com", 443, lambda _, data: heard.append(data), on_close
    )
    handle.send(b"ping")
    handle.close_write()
    assert closed.wait(5)
    assert heard == [b"PING"]
    assert peer.sent[1].meta == {"op": "connect", "host": "example.com", "port": 443}


def test_a_lost_connection_fails_everything_in_flight() -> None:
    peer = Peer(hello)
    client = RemoteClient(peer)
    client.start()
    ended = threading.Event()
    errors: list[OSError | None] = []

    def on_exit(result: dict[str, Any] | None, error: OSError | None) -> None:
        errors.append(error)
        ended.set()

    client.start_exec(["sleep"], "/", {}, ignore, on_exit)
    peer.inbox.put(ProtocolError("torn"))
    assert ended.wait(5)
    assert isinstance(errors[0], ConnectionResetError)
    client.close()


def test_a_closed_client_refuses_new_requests() -> None:
    client = RemoteClient(Peer(hello))
    client.start()
    client.close()
    client.close()
    with pytest.raises(ConnectionResetError):
        client.listdir("/")


def test_a_send_that_fails_is_a_connection_reset() -> None:
    peer = Peer(hello)
    client = RemoteClient(peer)
    client.start()
    peer.shut = True
    with pytest.raises(ConnectionResetError):
        client.unlink("/x")
    client.close()


def test_frames_for_nobody_are_ignored(
    opened: Opener,
) -> None:
    client, peer = opened(
        lambda frame: [Frame.reply(frame.msg_id + 1000), Frame.reply(frame.msg_id)]
    )
    peer.inbox.put(Frame.chunk(4242, Stream.DATA, b"stray"))
    assert client.listdir("/") == {}
