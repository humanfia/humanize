"""One connection served from frames held in memory, answering into a buffer."""

from __future__ import annotations

import errno
import io
import os
import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.proto import PROTOCOL_VERSION, Channel, Frame, Kind, Op, Stream
from hmz.coganchor.serve import fencing
from hmz.coganchor.serve.exports import ExportTable
from hmz.coganchor.serve.server import Server
from tests.unit.coganchor.doubles_u8 import Kept, frames, names, wire

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def fences_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fencing, "able", lambda: {"fs": False, "net": False})


@pytest.fixture
def real(tmp_path: Path) -> Path:
    root = tmp_path / "real"
    root.mkdir()
    (root / "f.txt").write_bytes(b"hello")
    return root


@pytest.fixture
def table(real: Path) -> ExportTable:
    return ExportTable.parse([f"/w:{real}"], insensitive=False)


def hello(msg_id: int = 1, **meta: Any) -> Frame:
    return Frame(
        Kind.REQ, msg_id, {"op": Op.HELLO.value, "version": PROTOCOL_VERSION} | meta
    )


def served(table: ExportTable, *asked: Frame, token: str | None = None) -> list[Frame]:
    channel, sent = wire(asked)
    Server(channel, table, token).serve()
    return frames(sent.getvalue())


def replies(got: list[Frame]) -> dict[int, Frame]:
    return {one.msg_id: one for one in got if one.kind in (Kind.RSP, Kind.ERR)}


def test_the_handshake_says_what_this_machine_is(
    table: ExportTable, real: Path
) -> None:
    (said,) = served(table, hello())
    assert said.kind is Kind.RSP
    assert said.meta["version"] == PROTOCOL_VERSION
    assert said.meta["platform"] == sys.platform
    assert said.meta["pid"] == os.getpid()
    assert said.meta["exports"] == [{"virtual": "/w", "real": str(real)}]
    assert said.meta["fence"] == {"fs": False, "net": False}


def test_a_client_of_another_version_is_refused_and_hung_up_on(
    table: ExportTable,
) -> None:
    got = served(table, hello(version=99), Frame.request(2, Op.STAT, path="/w"))
    assert [one.kind for one in got] == [Kind.ERR]
    assert got[0].meta["errno"] == errno.EPROTO
    assert "protocol 99" in got[0].meta["strerror"]


@pytest.mark.parametrize("token", [None, "wrong"])
def test_without_the_token_nothing_is_served(
    table: ExportTable, token: str | None
) -> None:
    asked = [hello(token=token)] if token else []
    got = replies(
        served(table, *asked, Frame.request(2, Op.STAT, path="/w"), token="tok")
    )
    assert got[2].kind is Kind.ERR
    assert got[2].meta["errno"] == errno.EACCES


def test_with_the_token_everything_is(table: ExportTable) -> None:
    got = replies(
        served(
            table, hello(token="tok"), Frame.request(2, Op.STAT, path="/w"), token="tok"
        )
    )
    assert got[1].kind is Kind.RSP
    assert got[2].kind is Kind.RSP
    assert got[2].meta["kind"] == "dir"


@pytest.mark.parametrize(
    ("asked", "code"),
    [
        (Frame(Kind.REQ, 2, {"op": "teleport"}), errno.ENOSYS),
        (Frame(Kind.REQ, 2, {}), errno.ENOSYS),
        (Frame.request(2, Op.STAT), errno.EINVAL),
        (Frame.request(2, Op.CHMOD, path="/w/f.txt"), errno.EINVAL),
        (Frame.request(2, Op.STAT, path="/etc"), errno.EACCES),
        (Frame.request(2, Op.STAT, path="relative"), errno.EINVAL),
        (Frame.request(2, Op.STAT, path="/w/missing"), errno.ENOENT),
        (Frame.request(2, Op.SIGNAL), errno.EINVAL),
    ],
)
def test_a_request_that_cannot_be_served_fails_with_its_errno(
    table: ExportTable, asked: Frame, code: int
) -> None:
    got = replies(served(table, hello(), asked))
    assert got[2].kind is Kind.ERR
    assert got[2].meta["errno"] == code


def test_the_simple_operations_are_carried_out(table: ExportTable, real: Path) -> None:
    got = replies(
        served(
            table,
            hello(),
            Frame.request(2, Op.MKDIR, path="/w/d/e", parents=True),
            Frame.request(3, Op.RENAME, src="/w/f.txt", dst="/w/d/g.txt"),
            Frame.request(4, Op.SYMLINK, target="g.txt", path="/w/d/l"),
            Frame.request(5, Op.READLINK, path="/w/d/l"),
            Frame.request(6, Op.TRUNCATE, path="/w/d/g.txt", size=1),
            Frame.request(7, Op.LISTDIR, path="/w/d"),
            Frame.request(8, Op.UNLINK, path="/w/d/l"),
            Frame.request(9, Op.RMDIR, path="/w/d/e"),
        )
    )
    assert all(one.kind is Kind.RSP for one in got.values())
    assert got[5].meta == {"target": "g.txt"}
    assert sorted(one["name"] for one in got[7].meta["entries"]) == ["e", "g.txt", "l"]
    assert names(real / "d") == ["g.txt"]
    assert (real / "d" / "g.txt").read_bytes() == b"h"


def test_a_file_is_read_as_chunks_then_a_reply(table: ExportTable) -> None:
    got = served(table, hello(), Frame.request(2, Op.READ, path="/w/f.txt"))
    chunks = [one for one in got if one.kind is Kind.CHUNK]
    assert [(one.msg_id, one.stream, one.body) for one in chunks] == [
        (2, Stream.DATA, b"hello")
    ]
    assert got[-1].kind is Kind.RSP
    assert got[-1].meta["size"] == 5


def test_a_file_is_written_from_its_chunks_once_ended(
    table: ExportTable, real: Path
) -> None:
    got = replies(
        served(
            table,
            hello(),
            Frame.request(2, Op.WRITE, b"first ", path="/w/new.txt", mode=0o100600),
            Frame.chunk(2, Stream.DATA, b"second"),
            Frame.end(2),
            Frame.chunk(2, Stream.DATA, b"after the end, for nobody"),
        )
    )
    assert got[2].kind is Kind.RSP
    assert got[2].meta["size"] == 12
    assert (real / "new.txt").read_bytes() == b"first second"


def test_a_write_cut_off_by_the_peer_leaves_nothing(
    table: ExportTable, real: Path
) -> None:
    got = replies(
        served(
            table,
            hello(),
            Frame.request(2, Op.WRITE, path="/w/new.txt"),
            Frame.chunk(2, Stream.DATA, b"partial"),
        )
    )
    assert 2 not in got
    assert names(real) == ["f.txt"]


def test_a_signal_for_nothing_running_is_answered(table: ExportTable) -> None:
    got = replies(
        served(table, hello(), Frame.request(2, Op.SIGNAL, target=99, sig=15))
    )
    assert got[2].kind is Kind.RSP


def test_frames_nobody_asked_for_are_ignored(table: ExportTable) -> None:
    got = served(
        table, hello(), Frame.reply(5), Frame.chunk(6, Stream.DATA, b"x"), Frame.end(7)
    )
    assert [one.msg_id for one in got] == [1]


def test_a_torn_stream_ends_the_connection_quietly(table: ExportTable) -> None:
    sent = Kept()
    reader = io.BytesIO(hello().encode() + hello(2).encode()[:-3])
    Server(Channel(reader, sent), table).serve()
    assert [one.msg_id for one in frames(sent.getvalue())] == [1]
