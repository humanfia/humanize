"""`runs.*`, `backups.*` and `files.*` served over a real socket pair, as a client calls them.

An epic written down is listed, read, carried away a chunk at a time as the archive the web
interface hands a browser, and read back in from the chunks it was sent as. A chat is no epic:
`chat.*` reads it, by its name, off a record of its own.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import io
import json
import shutil
import socket
import tarfile
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon.api import backups, chats, files, runs
from hmz.rpc import PROTOCOL, Call, Dispatcher, Peer, RpcError, admit, hello
from hmz.runtime.epic import Epic
from hmz.runtime.epic import chats as written_chats
from tests.integration.doubles_core import install
from tests.integration.doubles_daemon import old_chat

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: How much each chunk of these asks for: small, so that an archive takes several.
_CHUNK = 4096


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project, and an epic an earlier hmz recorded for a chat written down in it."""
    at = install(tmp_path, monkeypatch)
    old_chat(at, "hello there")
    return at


@pytest.fixture
def client(project: Path) -> Iterator[Peer]:
    """A client's end of a session whose other end serves the runs and chats, greeted."""
    del project
    served = Dispatcher()

    def greets(call: Call) -> dict[str, Any]:
        admit(call.params["protocol"])
        return {"daemon_id": "d", "protocol": PROTOCOL, "paired": True}

    served.register("session.hello", greets)
    for family in (runs, chats, backups, files):
        for name, handler in family.METHODS.items():
            served.register(name, handler)
    ours, theirs = socket.socketpair()
    daemon = Peer(ours, served, name="daemon")
    end = Peer(theirs, name="client")
    hello(end, "test", "cli", timeout=5)
    try:
        yield end
    finally:
        end.close()
        daemon.close()


def _refused(client: Peer, method: str, params: dict[str, Any]) -> RpcError:
    with pytest.raises(RpcError) as refused:
        client.call(method, params, timeout=30)
    return refused.value


def _pulled(client: Peer, handle: str) -> bytes:
    """Every byte of a read handle, a chunk at a time."""
    got = b""
    while True:
        said = client.call(
            "files.read",
            {"handle": handle, "offset": len(got), "length": _CHUNK},
            timeout=30,
        )
        got += base64.b64decode(said["data"])
        if said["eof"]:
            return got


def _sent(client: Peer, name: str, data: bytes) -> str:
    """A write handle holding the bytes, sent a chunk at a time."""
    made = client.call("files.create", {"name": name, "size": len(data)}, timeout=30)
    handle: str = made["handle"]
    for at in range(0, len(data), _CHUNK):
        chunk = base64.b64encode(data[at : at + _CHUNK]).decode()
        said = client.call(
            "files.write", {"handle": handle, "offset": at, "data": chunk}, timeout=30
        )
        assert said == {"size": min(len(data), at + _CHUNK)}
    return handle


def _members(archive: bytes) -> dict[str, Any]:
    """What an archive holds, file by file: the same whenever it was packed.

    Which is every byte of every file, but for the moment the manifest says it was made.
    """
    held: dict[str, Any] = {}
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(archive))) as reading:
        for member in reading.getmembers():
            with contextlib.closing(reading.extractfile(member) or io.BytesIO()) as one:
                held[member.name] = one.read()
            if member.name.endswith("/manifest.json"):
                held[member.name] = json.loads(held[member.name]) | {"made": ""}
    return held


def test_an_epic_is_listed_read_carried_away_in_chunks_and_read_back_in(
    project: Path, client: Peer
) -> None:
    listed = client.call("runs.list", {"workspace": str(project)}, timeout=30)
    (run,) = listed["runs"]
    name = run["name"]
    # An epic an earlier hmz recorded for a chat reads as a chat, of no flow.
    assert (run["kind"], run["flow"], run["task"], listed["total"]) == (
        "chat",
        "",
        "hello there",
        1,
    )
    one = client.call("runs.get", {"name": name}, timeout=30)
    assert (one["name"], one["task"], one["calls"]) == (name, "hello there", [])

    bundle = client.call("runs.bundle", {"name": name}, timeout=30)
    assert (bundle["filename"], bundle["type"]) == (
        f"{name}.hmzepic",
        "application/vnd.hmz.epic+gzip",
    )
    archive = _pulled(client, bundle["handle"])
    assert len(archive) == bundle["size"]
    # Packed again, it holds the same.
    again = client.call("runs.bundle", {"name": name}, timeout=30)
    assert _members(archive) == _members(_pulled(client, again["handle"]))
    assert client.call("files.close", {"handle": bundle["handle"]}, timeout=30) == {}

    shutil.rmtree(one["at"])
    gone = _refused(client, "runs.get", {"name": name})
    assert (gone.code, gone.message) == (404, f"There is no epic {name}.")
    handle = _sent(client, bundle["filename"], archive)
    imported = client.call("runs.import", {"handle": handle}, timeout=30)
    assert imported == {
        "name": name,
        "workspace": str(project.resolve()),
        "resumable": False,
        "why": "",
    }
    assert client.call("runs.get", {"name": name}, timeout=30)["name"] == name

    again = _refused(
        client, "runs.import", {"handle": _sent(client, bundle["filename"], archive)}
    )
    assert (again.code, again.data) == (409, {"name": name})
    assert "is already here" in again.message


def test_a_chat_is_read_by_chat_get_and_is_none_of_the_runs(
    project: Path, client: Peer
) -> None:
    (old,) = client.call("runs.list", {"workspace": str(project)}, timeout=30)["runs"]
    with Epic("", "plain words", project, kind="chat") as plain:
        plain.stopped()
    with Epic(
        "",
        "start the flows",
        project,
        kind="chat",
        prefer="flow",
        permission="read-only",
    ) as chat:
        chat.stopped()
    name = chat.path.name

    # The runs are as they were: the one epic, and neither chat by any name for it.
    listed = client.call("runs.list", {"workspace": str(project)}, timeout=30)
    assert [one["name"] for one in listed["runs"]] == [old["name"]]
    assert (listed["total"], listed["flows"]) == (1, ["chat"])
    for method in ("runs.get", "runs.trace", "runs.bundle", "runs.backup"):
        gone = _refused(client, method, {"name": name})
        assert (gone.code, gone.message) == (404, f"There is no epic {name}.")
    # No kind is asked of the runs any more.
    invalid = _refused(client, "runs.list", {"kind": "chat"})
    assert (invalid.code, invalid.message) == (-32602, "runs.list takes no kind.")
    # Nor is anything of a chat's said of an epic: not even of one recorded for a chat.
    whole = client.call("runs.get", {"name": old["name"]}, timeout=30)
    assert whole["kind"] == "chat"
    for absent in ("earlier", "permission", "prefer"):
        assert absent not in whole

    # The chats are listed newest first, and the override each records is read with it.
    said = client.call("chat.list", {"workspace": str(project)}, timeout=30)
    assert [one["id"] for one in said["chats"]] == [name, plain.path.name]
    assert [(one["permission"], one["state"]) for one in said["chats"]] == [
        ("read-only", "resting"),
        ("workspace-write", "resting"),
    ]
    assert client.call("chat.get", {"chat": name}, timeout=30)["prefer"] == "flow"
    assert (
        client.call("chat.get", {"chat": plain.path.name}, timeout=30)["prefer"] == ""
    )
    absent = _refused(client, "chat.get", {"chat": old["name"]})
    assert (absent.code, absent.message) == (404, f"There is no chat {old['name']}.")

    # Deleted, a chat is gone from disk; the epic recorded for a chat is still there.
    assert client.call("chat.delete", {"chat": name}, timeout=30) == {}
    assert written_chats() == [plain.path]
    assert not chat.path.exists()
    assert (
        client.call("runs.get", {"name": old["name"]}, timeout=30)["name"]
        == old["name"]
    )


def test_a_handle_is_refused_what_it_cannot_carry(client: Peer) -> None:
    unknown = _refused(
        client, "files.read", {"handle": "nope", "offset": 0, "length": 1}
    )
    assert (unknown.code, unknown.message) == (404, "There is no file nope.")

    handle = client.call("files.create", {"name": "x.hmzepic", "size": 4}, timeout=30)[
        "handle"
    ]
    big = base64.b64encode(bytes(files.CHUNK + 1)).decode()
    oversize = _refused(
        client, "files.write", {"handle": handle, "offset": 0, "data": big}
    )
    assert oversize.code == 413
    past = _refused(
        client,
        "files.write",
        {"handle": handle, "offset": 9, "data": base64.b64encode(b"x").decode()},
    )
    assert (past.code, past.message) == (409, "Write at 0.")
    early = _refused(client, "runs.import", {"handle": handle})
    assert (early.code, early.message) == (409, "The file is not whole yet.")
    # Given to the import, which took it.
    taken = _refused(client, "files.close", {"handle": handle})
    assert (taken.code, taken.message) == (404, f"There is no file {handle}.")

    length = _refused(
        client, "files.read", {"handle": "nope", "offset": 0, "length": files.CHUNK + 1}
    )
    assert length.code == -32602
    absent = _refused(client, "runs.bundle", {"name": "no-such-epic"})
    assert (absent.code, absent.message) == (404, "There is no epic no-such-epic.")
