"""`hmz.daemon.api.files`: a file carried a chunk at a time, through a handle of one session's."""

from __future__ import annotations

import base64
import threading
import time
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon.api.files import CHUNK, LARGEST, METHODS, reading, taken
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.rpc import Call, Peer


class _Session:
    """A session as a handle reads it: whether it has closed, and waiting for it to."""

    def __init__(self) -> None:
        self._closed = threading.Event()
        self._closing: list[Callable[[], None]] = []

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout)

    def closing(self, told: Callable[[], None]) -> None:
        self._closing.append(told)

    def close(self) -> None:
        self._closed.set()
        for told in self._closing:
            told()


class _Call:
    """A call as a handler reads it."""

    def __init__(self, peer: _Session, method: str, **params: Any) -> None:
        self.peer = peer
        self.method = method
        self.params = params


@pytest.fixture
def session() -> Iterator[_Session]:
    one = _Session()
    yield one
    one.close()


def _call(session: _Session, method: str, **params: Any) -> Any:
    return METHODS[method](cast("Call", _Call(session, method, **params)))


def _refused(session: _Session, method: str, **params: Any) -> RpcError:
    with pytest.raises(RpcError) as refused:
        _call(session, method, **params)
    return refused.value


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _created(session: _Session, name: str, size: int) -> str:
    return _call(session, "files.create", name=name, size=size)["handle"]


def test_every_method_of_the_family_is_served() -> None:
    assert set(METHODS) == {"files.create", "files.write", "files.read", "files.close"}


def test_a_file_not_whole_is_taken_all_the_same(session: _Session) -> None:
    handle = _created(session, "a.hmzepic", 5)
    _call(session, "files.write", handle=handle, offset=0, data=_b64(b"ab"))

    with pytest.raises(RpcError) as early:
        taken(cast("Call", _Call(session, "runs.import")), handle)

    assert (early.value.code, early.value.message) == (
        409,
        "The file is not whole yet.",
    )
    assert _refused(session, "files.close", handle=handle).code == 404


def test_a_file_written_in_chunks_is_taken_whole_under_its_name(
    session: _Session,
) -> None:
    handle = _created(session, "a.hmzepic", 5)

    assert _call(session, "files.write", handle=handle, offset=0, data=_b64(b"ab")) == {
        "size": 2
    }
    assert _call(
        session, "files.write", handle=handle, offset=2, data=_b64(b"cde")
    ) == {"size": 5}
    name, at = taken(cast("Call", _Call(session, "runs.import")), handle)

    assert (name, at.read_bytes()) == ("a.hmzepic", b"abcde")
    # The method's now, which no call names again.
    assert _refused(session, "files.close", handle=handle).code == 404


@pytest.mark.parametrize(
    ("offset", "data", "code", "message"),
    [
        (1, _b64(b"x"), 409, "Write at 0."),
        (0, _b64(b"xyzw"), 413, "That is more than the 3 bytes declared."),
        (0, _b64(bytes(CHUNK + 1)), 413, "That is more than a call here may carry."),
        (0, "not base64!", 400, "data is not base64."),
    ],
    # Each named, not spelled out: a chunk too big as its own name is a line of megabytes.
    ids=["out-of-place", "past-declared", "past-a-chunk", "not-base64"],
)
def test_a_chunk_out_of_place_or_too_big_is_refused(
    session: _Session, offset: int, data: str, code: int, message: str
) -> None:
    handle = _created(session, "x", 3)

    refused = _refused(session, "files.write", handle=handle, offset=offset, data=data)

    assert (refused.code, refused.message) == (code, message)


@pytest.mark.parametrize("size", [-1, LARGEST + 1])
def test_a_file_bigger_than_any_is_refused(session: _Session, size: int) -> None:
    assert _refused(session, "files.create", name="x", size=size).code == -32602


def _own(tmp_path: Path) -> Path:
    """A file alone in a directory of its own, as a read handle is made of one."""
    (tmp_path / "own").mkdir()
    at = tmp_path / "own" / "e.hmzepic"
    at.write_bytes(b"0123456789")
    return at


def test_a_file_is_read_a_chunk_at_a_time_to_its_end(
    session: _Session, tmp_path: Path
) -> None:
    at = _own(tmp_path)
    handle = reading(cast("Peer", session), at)

    first = _call(session, "files.read", handle=handle, offset=0, length=4)
    last = _call(session, "files.read", handle=handle, offset=4, length=100)
    past = _call(session, "files.read", handle=handle, offset=40, length=4)

    assert (base64.b64decode(first["data"]), first["eof"]) == (b"0123", False)
    assert (base64.b64decode(last["data"]), last["eof"]) == (b"456789", True)
    assert past == {"data": "", "eof": True}
    for length in (0, CHUNK + 1):
        refused = _refused(
            session, "files.read", handle=handle, offset=0, length=length
        )
        assert refused.code == -32602
    # A read handle is written by nobody.
    written = _refused(session, "files.write", handle=handle, offset=0, data="")
    assert (written.code, written.message) == (404, f"There is no file {handle}.")

    assert _call(session, "files.close", handle=handle) == {}
    assert not at.exists()


def test_a_handle_is_no_other_sessions(session: _Session) -> None:
    handle = _created(session, "x", 1)
    other = _Session()
    try:
        for method, params in (
            ("files.write", {"offset": 0, "data": _b64(b"x")}),
            ("files.read", {"offset": 0, "length": 1}),
            ("files.close", {}),
        ):
            refused = _refused(other, method, handle=handle, **params)
            assert (refused.code, refused.message) == (
                404,
                f"There is no file {handle}.",
            )
        assert _call(session, "files.write", handle=handle, offset=0, data=_b64(b"x"))
    finally:
        other.close()


def test_a_handle_ends_with_its_session(session: _Session, tmp_path: Path) -> None:
    at = _own(tmp_path)
    reading(cast("Peer", session), at)

    session.close()

    deadline = time.monotonic() + 5
    while at.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not at.exists()
