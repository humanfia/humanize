"""`hmz.daemon.api.runs`: what a call to `runs.*` is refused for before any epic is read."""

from __future__ import annotations

import base64
import threading
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon.api import files, runs
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.rpc import Call


class _Session:
    """A session as a handle reads it: whether it has closed, and waiting for it to."""

    def __init__(self) -> None:
        self._closed = threading.Event()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._closed.wait(timeout)

    def close(self) -> None:
        self._closed.set()


class _Call:
    """A call as a handler reads it."""

    def __init__(self, peer: _Session, method: str, **params: Any) -> None:
        self.peer = peer
        self.method = method
        self.params = params


class _Runs:
    """The runs, as far as an import reads them: what it was handed."""

    def __init__(self) -> None:
        self.archives: list[tuple[str, bytes]] = []

    def imported(self, archive: Path) -> dict[str, Any]:
        self.archives.append((archive.name, archive.read_bytes()))
        return {"name": "e", "workspace": "/w", "resumable": True, "why": ""}


@pytest.fixture
def session() -> Iterator[_Session]:
    one = _Session()
    yield one
    one.close()


@pytest.fixture
def held(monkeypatch: pytest.MonkeyPatch) -> _Runs:
    fake = _Runs()
    monkeypatch.setattr(runs, "RUNS", fake)
    return fake


def _call(session: _Session, method: str, **params: Any) -> Any:
    table = {**runs.METHODS, **files.METHODS}
    return table[method](cast("Call", _Call(session, method, **params)))


def _refused(session: _Session, method: str, **params: Any) -> RpcError:
    with pytest.raises(RpcError) as refused:
        _call(session, method, **params)
    return refused.value


def _sent(session: _Session, name: str, data: bytes) -> str:
    handle = _call(session, "files.create", name=name, size=len(data))["handle"]
    encoded = base64.b64encode(data).decode()
    _call(session, "files.write", handle=handle, offset=0, data=encoded)
    return handle


def test_every_method_of_the_family_is_served() -> None:
    assert set(runs.METHODS) == {
        f"runs.{one}"
        for one in (
            "list",
            "get",
            "trace",
            "timeline",
            "span",
            "bundle",
            "backup",
            "import",
            "usage",
        )
    }


@pytest.mark.parametrize(
    ("method", "params", "message"),
    [
        ("runs.list", {"limit": 0}, "runs.list takes limit as integer from 1 to 200."),
        (
            "runs.list",
            {"limit": 201},
            "runs.list takes limit as integer from 1 to 200.",
        ),
        ("runs.list", {"offset": -1}, "runs.list takes offset as integer from 0."),
        ("runs.usage", {"days": 0}, "runs.usage takes days as integer from 1 to 365."),
        (
            "runs.usage",
            {"days": 366},
            "runs.usage takes days as integer from 1 to 365.",
        ),
        (
            "runs.backup",
            {"name": "e", "to": [1]},
            "runs.backup takes to as array of strings.",
        ),
        ("runs.import", {}, "runs.import takes handle or path, one of them."),
        (
            "runs.import",
            {"handle": "h", "path": "/x"},
            "runs.import takes handle or path, one of them.",
        ),
    ],
)
def test_parameters_out_of_their_range_are_refused(
    session: _Session, method: str, params: dict[str, Any], message: str
) -> None:
    refused = _refused(session, method, **params)

    assert (refused.code, refused.message) == (-32602, message)


def test_a_workspace_is_a_whole_path_to_a_directory(tmp_path: Path) -> None:
    assert runs.workspace(str(tmp_path)) == str(tmp_path)
    with pytest.raises(RpcError) as relative:
        runs.workspace("w")
    assert (relative.value.code, relative.value.message) == (
        400,
        "Say the workspace as a whole path, not w.",
    )
    with pytest.raises(RpcError) as missing:
        runs.workspace(str(tmp_path / "gone"))
    assert (missing.value.code, missing.value.message) == (
        404,
        f"There is no directory {tmp_path / 'gone'}.",
    )


@pytest.mark.parametrize(
    ("said", "code", "data"),
    [
        ("an epic is already here, at /h/epics/-w/an epic", 409, {"name": "an epic"}),
        ("x.hmzepic is not a bundle Humanize can read: not a gzip file", 400, None),
    ],
)
def test_an_import_refused_says_why_and_names_the_epic_already_here(
    said: str, code: int, data: dict[str, str] | None
) -> None:
    refused = runs.refused(ValueError(said))

    assert (refused.code, refused.message, refused.data) == (code, f"{said}.", data)


def test_an_archive_sent_is_imported_under_its_name_and_taken(
    session: _Session, held: _Runs
) -> None:
    handle = _sent(session, "e.hmzepic", b"bytes")

    assert _call(session, "runs.import", handle=handle)["name"] == "e"
    assert held.archives == [("e.hmzepic", b"bytes")]
    gone = _refused(session, "files.close", handle=handle)
    assert (gone.code, gone.message) == (404, f"There is no file {handle}.")


@pytest.mark.parametrize("name", ["", "..", "a/b", "a\\b", "a\0b", "x" * 256])
def test_an_archive_sent_under_no_file_name_is_refused_and_taken(
    session: _Session, held: _Runs, name: str
) -> None:
    handle = _sent(session, name, b"x")

    refused = _refused(session, "runs.import", handle=handle)

    assert (refused.code, refused.message) == (400, "That is not a file name.")
    assert not held.archives
    assert _refused(session, "files.close", handle=handle).code == 404


def test_an_archive_named_by_a_path_is_a_whole_one(
    session: _Session, held: _Runs
) -> None:
    refused = _refused(session, "runs.import", path="x.hmzepic")

    assert (refused.code, refused.message) == (
        400,
        "Say path as a whole path on this machine.",
    )
    assert not held.archives
