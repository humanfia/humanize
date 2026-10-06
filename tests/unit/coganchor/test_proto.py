"""The wire protocol: frames, the channel carrying them, and the path rules both halves share."""

from __future__ import annotations

import errno
import io
import json
import struct
import threading
from typing import IO, Any, cast

import pytest

from hmz.coganchor.proto import (
    CASE_INSENSITIVE,
    CHUNK_SIZE,
    PLATFORMS,
    PROTOCOL_VERSION,
    Channel,
    Frame,
    Kind,
    Op,
    ProtocolError,
    RemoteOSError,
    Stream,
    hello_capabilities,
    hello_fences,
    path_key,
    path_within,
    rewrite_path_prefix,
    spelled_twice,
)
from tests.unit.coganchor.doubles_u8 import frames, wire


def through(frame: Frame) -> Frame:
    decoded = frames(frame.encode())
    assert len(decoded) == 1
    return decoded[0]


def raw(meta: bytes, body: bytes = b"", msg_id: int = 1) -> bytes:
    return struct.pack("<IIQ", len(meta) + len(body), len(meta), msg_id) + meta + body


def test_the_constants_are_what_both_halves_agree_on() -> None:
    assert PROTOCOL_VERSION == 1
    assert CHUNK_SIZE == 1 << 16
    assert frozenset({"darwin", "linux"}) == PLATFORMS
    assert frozenset({"darwin"}) == CASE_INSENSITIVE


@pytest.mark.parametrize(
    "frame",
    [
        Frame.request(7, Op.READ, path="/w/f"),
        Frame.request(2, Op.WRITE, b"\x00\xffbody", path="/w/f", mode=0o644),
        Frame.reply(3, size=4, entries=[{"name": "a"}]),
        Frame.chunk(4, Stream.STDERR, bytes(range(256)) * 300),
        Frame.end(5, Stream.STDIN),
        Frame.error(6, FileNotFoundError(errno.ENOENT, "No such file", "/gone")),
        Frame(Kind.RSP, 2**64 - 1),
    ],
)
def test_a_frame_survives_the_wire(frame: Frame) -> None:
    assert through(frame) == frame


@pytest.mark.parametrize(
    ("frame", "kind"),
    [
        (Frame.request(1, Op.HELLO), Kind.REQ),
        (Frame.reply(1), Kind.RSP),
        (Frame.error(1, OSError(errno.EIO, "x")), Kind.ERR),
        (Frame.chunk(1, Stream.DATA, b"x"), Kind.CHUNK),
        (Frame.end(1), Kind.END),
    ],
)
def test_each_constructor_makes_its_kind(frame: Frame, kind: Kind) -> None:
    assert frame.kind is kind


def test_a_request_names_its_operation() -> None:
    assert Frame.request(1, Op.LISTDIR, path="/").op is Op.LISTDIR


@pytest.mark.parametrize("meta", [{}, {"op": "teleport"}])
def test_an_unknown_or_missing_operation_reads_as_none(meta: dict[str, Any]) -> None:
    assert Frame(Kind.REQ, 1, meta).op is None


def test_a_stream_defaults_to_data() -> None:
    assert Frame(Kind.CHUNK, 1).stream is Stream.DATA
    assert Frame.end(1).stream is Stream.DATA


def test_the_header_counts_what_follows_it() -> None:
    blob = Frame.chunk(9, Stream.STDOUT, b"abc").encode()
    payload, meta, msg_id = struct.unpack("<IIQ", blob[:16])
    assert payload == len(blob) - 16
    assert msg_id == 9
    assert json.loads(blob[16 : 16 + meta]) == {"s": 1, "k": "c"}
    assert blob.endswith(b"abc")


def test_an_error_frame_carries_the_errno_across() -> None:
    sent = Frame.error(1, PermissionError(errno.EACCES, "Permission denied", "/x"))
    restored = RemoteOSError.from_meta(through(sent).meta)
    assert isinstance(restored, OSError)
    assert (restored.errno, restored.strerror, restored.filename) == (
        errno.EACCES,
        "Permission denied",
        "/x",
    )


def test_an_error_without_words_still_says_something() -> None:
    meta = Frame.error(1, OSError()).meta
    assert meta == {"errno": 0, "strerror": "remote error", "filename": None}
    assert Frame.error(1, OSError("bare")).meta["strerror"] == "bare"


def test_a_filename_that_is_not_text_is_left_behind() -> None:
    assert Frame.error(1, OSError(errno.EIO, "x", b"/bytes")).meta["filename"] is None


def test_a_remote_error_read_from_nothing_is_errno_nought() -> None:
    restored = RemoteOSError.from_meta({})
    assert (restored.errno, restored.strerror) == (0, "remote error")


def test_a_clean_end_of_stream_is_none() -> None:
    assert Channel(io.BytesIO(), io.BytesIO()).recv() is None


def test_frames_arrive_in_order_and_then_the_end() -> None:
    channel, _ = wire([Frame.request(1, Op.STAT, path="/a"), Frame.end(1)])
    first, second = channel.recv(), channel.recv()
    assert first is not None
    assert second is not None
    assert (first.msg_id, first.kind, second.kind) == (1, Kind.REQ, Kind.END)
    assert channel.recv() is None


class Trickle(io.RawIOBase):
    """A reader handing back three bytes a call, as a small pipe would."""

    def __init__(self, blob: bytes) -> None:
        self._blob = blob

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        taken, self._blob = self._blob[: min(size, 3)], self._blob[min(size, 3) :]
        return taken


def test_a_frame_read_in_pieces_is_one_frame() -> None:
    frame = Frame.chunk(1, Stream.DATA, b"x" * 100)
    got = Channel(cast("IO[bytes]", Trickle(frame.encode())), io.BytesIO()).recv()
    assert got == frame


@pytest.mark.parametrize(
    ("blob", "says"),
    [
        (Frame.request(1, Op.HELLO).encode()[:-2], "truncated"),
        (Frame.request(1, Op.HELLO).encode()[:10], "truncated"),
        (struct.pack("<IIQ", 1, 2, 1) + b"xx", "implausible"),
        (struct.pack("<IIQ", (1 << 30) + 1, 0, 1), "implausible"),
        (raw(b"{nope"), "malformed"),
        (raw(b"\xff\xfe"), "malformed"),
        (raw(b"[1, 2]"), "not an object"),
        (raw(b"{}"), "invalid frame kind"),
        (raw(b'{"k": "?"}'), "invalid frame kind"),
    ],
)
def test_malformed_input_is_a_protocol_error(blob: bytes, says: str) -> None:
    with pytest.raises(ProtocolError, match=says):
        Channel(io.BytesIO(blob), io.BytesIO()).recv()


class Broken(io.RawIOBase):
    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        raise OSError(errno.EIO, "gone")

    def write(self, b: Any) -> int:
        raise BrokenPipeError(errno.EPIPE, "gone")


def test_a_failing_read_is_a_protocol_error() -> None:
    with pytest.raises(ProtocolError, match="read failed"):
        Channel(cast("IO[bytes]", Broken()), io.BytesIO()).recv()


def test_a_failing_send_closes_the_channel() -> None:
    channel = Channel(io.BytesIO(), cast("IO[bytes]", Broken()))
    with pytest.raises(ProtocolError, match="send failed"):
        channel.send(Frame.reply(1))
    with pytest.raises(ProtocolError, match="closed"):
        channel.send(Frame.reply(1))


def test_a_closed_channel_sends_nothing() -> None:
    channel, sent = wire()
    channel.send(Frame.reply(1))
    channel.close()
    channel.close()
    with pytest.raises(ProtocolError, match="closed"):
        channel.send(Frame.reply(2))
    assert [one.msg_id for one in frames(sent.getvalue())] == [1]


def test_sends_from_many_threads_never_interleave() -> None:
    channel, sent = wire()

    def send(number: int) -> None:
        for _ in range(50):
            channel.send(Frame.chunk(number, Stream.DATA, bytes([number]) * 1000))

    threads = [threading.Thread(target=send, args=(n,)) for n in range(1, 5)]
    for one in threads:
        one.start()
    for one in threads:
        one.join()
    got = frames(sent.getvalue())
    assert len(got) == 200
    assert all(one.body == bytes([one.msg_id]) * 1000 for one in got)


class Socketish:
    def __init__(self) -> None:
        self.shut: list[int] = []
        self.closed = False
        self.reading = io.BytesIO(Frame.reply(4).encode())
        self.writing = io.BytesIO()

    def makefile(self, mode: str) -> io.BytesIO:
        return self.reading if mode == "rb" else self.writing

    def shutdown(self, how: int) -> None:
        self.shut.append(how)

    def close(self) -> None:
        self.closed = True


def test_a_channel_over_a_socket_owns_it() -> None:
    held = Socketish()
    channel = Channel.from_socket(held)
    got = channel.recv()
    assert got is not None
    assert got.msg_id == 4
    channel.close()
    assert held.shut
    assert held.closed


@pytest.mark.parametrize(
    ("said", "names"),
    [
        ({"platform": "linux"}, {"linux"}),
        ({"platform": "darwin"}, {"darwin"}),
        ({"platform": "win32"}, set[str]()),
        ({}, set[str]()),
    ],
)
def test_the_handshake_names_only_platforms_known_here(
    said: dict[str, Any], names: set[str]
) -> None:
    assert hello_capabilities(said) == names


@pytest.mark.parametrize(
    ("said", "net", "able"),
    [
        ({}, False, False),
        ({"fence": "yes"}, False, False),
        ({"fence": {"fs": True}}, False, True),
        ({"fence": {"fs": True}}, True, False),
        ({"fence": {"fs": True, "net": True}}, True, True),
        ({"fence": {"fs": False, "net": True}}, False, False),
        ({"fence": {"fs": 1}}, False, False),
    ],
)
def test_a_target_fences_only_what_it_said_it_could(
    said: dict[str, Any], net: bool, able: bool
) -> None:
    assert hello_fences(said, net=net) is able


@pytest.mark.parametrize(
    ("path", "fold", "key"),
    [
        ("/private/tmp/x", False, "/tmp/x"),
        ("/private/var", False, "/var"),
        ("/private/etc/hosts", False, "/etc/hosts"),
        ("/private/various", False, "/private/various"),
        ("/PRIVATE/tmp", False, "/PRIVATE/tmp"),
        ("/private", False, "/private"),
        ("/srv/private/tmp", False, "/srv/private/tmp"),
        ("/Users/Me", True, "/users/me"),
        ("/private/tmp/A", True, "/tmp/a"),
    ],
)
def test_a_path_key_folds_the_aliases_a_mac_has(
    path: str, fold: bool, key: str
) -> None:
    assert path_key(path, fold_case=fold) == key


@pytest.mark.parametrize(
    ("path", "root", "fold", "below"),
    [
        ("/w/a/b", "/w", False, "a/b"),
        ("/w", "/w", False, ""),
        ("/w/", "/w/", False, ""),
        ("/wide", "/w", False, None),
        ("/x/w", "/w", False, None),
        ("/anything/at/all", "/", False, "anything/at/all"),
        ("/private/tmp/w/f", "/tmp/w", False, "f"),
        ("/tmp/w/f", "/private/tmp/w", False, "f"),
        ("/W/Sub/File", "/w", True, "Sub/File"),
        ("/W/f", "/w", False, None),
        ("/STRASSE/f", "/straße", True, None),
    ],
)
def test_a_path_within_a_root_is_cut_as_it_was_spelled(
    path: str, root: str, fold: bool, below: str | None
) -> None:
    assert path_within(path, root, fold_case=fold) == below


@pytest.mark.parametrize(
    ("root", "twice"),
    [
        ("/srv/work", False),
        ("/tmp/work", True),
        ("/private/var/x", True),
        ("/", True),
        ("/private", True),
        ("/private/other", False),
    ],
)
def test_a_root_is_spelled_twice_where_a_mac_aliases_it(root: str, twice: bool) -> None:
    assert spelled_twice(root) is twice


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cat /w/f", "cat /real/f"),
        ("/w", "/real"),
        ("cd '/w'", "cd '/real'"),
        ("--dir=/w/x", "--dir=/real/x"),
        ("a:/w;b", "a:/real;b"),
        ("echo hello/w/x", "echo hello/w/x"),
        ("--flag=/wide", "--flag=/wide"),
        ("/w/a /w/b", "/real/a /real/b"),
        ("nothing here", "nothing here"),
    ],
)
def test_a_prefix_is_rewritten_only_where_it_names_a_path(
    text: str, expected: str
) -> None:
    assert rewrite_path_prefix(text, "/w", "/real") == expected


def test_a_prefix_is_matched_by_case_only_when_asked() -> None:
    assert rewrite_path_prefix("ls /W/f", "/w", "/real") == "ls /W/f"
    assert (
        rewrite_path_prefix("ls /W/f", "/w", "/real", insensitive=True) == "ls /real/f"
    )


def test_a_replacement_is_taken_literally() -> None:
    assert rewrite_path_prefix("/w/f", "/w", r"C:\real\1") == r"C:\real\1/f"


def test_an_identity_rewrite_changes_nothing() -> None:
    assert rewrite_path_prefix("/w/f", "/w", "/w") == "/w/f"
