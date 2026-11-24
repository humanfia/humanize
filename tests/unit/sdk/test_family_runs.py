"""`Client.runs`, `Client.backups` and `Client.files`: typed calls, the client mocked."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest

from hmz.sdk import Refused
from hmz.sdk.families.backups import Backups, Stored, Target
from hmz.sdk.families.files import CHUNK, Chunk, Files
from hmz.sdk.families.runs import Bundle, Exported, Imported, Listing, Runs

if TYPE_CHECKING:
    from pathlib import Path


class Daemon:
    """What a daemon does with file handles and the methods given, as `Client.call` asks it."""

    def __init__(self, **answers: Any) -> None:
        self.answers = {
            name.replace("_", ".", 1): said for name, said in answers.items()
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.reading: dict[str, bytes] = {}
        self.writing: dict[str, bytearray] = {}
        self.closed: list[str] = []

    def call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        idem: str | None = None,
        seconds: float | None = None,
    ) -> Any:
        del seconds
        self.calls.append((method, params | ({"idem": idem} if idem else {})))
        if method == "files.create":
            self.writing["w1"] = bytearray()
            return {"handle": "w1"}
        if method == "files.write":
            held = self.writing[params["handle"]]
            assert params["offset"] == len(held)
            held += base64.b64decode(params["data"])
            return {"size": len(held)}
        if method == "files.read":
            data = self.reading[params["handle"]]
            some = data[params["offset"] : params["offset"] + params["length"]]
            return {
                "data": base64.b64encode(some).decode(),
                "eof": params["offset"] + len(some) >= len(data),
            }
        if method == "files.close":
            self.closed.append(params["handle"])
            return {}
        said: Any = self.answers[method]
        if isinstance(said, Exception):
            raise said
        if isinstance(said, list):
            return cast("list[Any]", said).pop(0)
        return said

    def asked(self, method: str) -> list[dict[str, Any]]:
        return [params for name, params in self.calls if name == method]


def _client(daemon: Daemon) -> mock.Mock:
    client = mock.Mock(spec=["call", "files"])
    client.call.side_effect = daemon.call
    client.files = Files(client)
    return client


def test_each_family_names_the_methods_it_makes() -> None:
    assert Runs.METHODS == (
        "runs.list",
        "runs.get",
        "runs.trace",
        "runs.timeline",
        "runs.span",
        "runs.bundle",
        "runs.backup",
        "runs.import",
        "runs.usage",
    )
    assert Backups.METHODS == ("backups.epics", "backups.pull")
    assert Files.METHODS == (
        "files.create",
        "files.write",
        "files.read",
        "files.close",
    )


def test_epics_are_listed_by_what_was_said_and_nothing_else() -> None:
    daemon = Daemon(
        runs_list={
            "runs": [{"name": "e1"}],
            "total": 3,
            "offset": 2,
            "limit": 1,
            "counts": {"done": 3},
            "flows": ["ralph"],
        }
    )

    found = Runs(_client(daemon)).list(query="parser", status="done", offset=2, limit=1)

    assert found == Listing([{"name": "e1"}], 3, 2, 1, {"done": 3}, ["ralph"])
    assert daemon.asked("runs.list") == [
        {"q": "parser", "status": "done", "offset": 2, "limit": 1}
    ]


def test_an_epic_is_read_back_whole_with_its_trace_and_timeline() -> None:
    daemon = Daemon(
        runs_get={"name": "e1", "task": "all of it"},
        runs_trace={"sessions": [{"key": "claude:1", "agent": "coder", "actions": []}]},
        runs_timeline={"layout": "L1", "tracks": []},
        runs_usage={"days_back": 7, "whole": {"runs": 1}},
    )
    runs = Runs(_client(daemon))

    assert runs.get("e1") == {"name": "e1", "task": "all of it"}
    assert runs.trace("e1") == [{"key": "claude:1", "agent": "coder", "actions": []}]
    assert runs.timeline("e1") == {"layout": "L1", "tracks": []}
    assert runs.usage(days=7, workspace="/w") == {"days_back": 7, "whole": {"runs": 1}}
    assert daemon.asked("runs.usage") == [{"days": 7, "workspace": "/w"}]


def test_a_span_is_read_in_the_layout_given_or_in_one_laid_out_first() -> None:
    daemon = Daemon(runs_timeline={"layout": "L2"}, runs_span={"id": 4, "cat": "tool"})
    runs = Runs(_client(daemon))

    assert runs.span("e1", 4, "L1") == {"id": 4, "cat": "tool"}
    assert daemon.asked("runs.timeline") == []
    assert runs.span("e1", 4) == {"id": 4, "cat": "tool"}

    assert daemon.asked("runs.span") == [
        {"name": "e1", "id": 4, "layout": "L1"},
        {"name": "e1", "id": 4, "layout": "L2"},
    ]


def test_an_epic_is_exported_to_a_file_a_chunk_at_a_time(tmp_path: Path) -> None:
    archive = bytes(range(256)) * 5000  # More than one chunk.
    assert len(archive) > CHUNK
    bundle: dict[str, Any] = {
        "handle": "r1",
        "filename": "e1.hmzepic",
        "size": len(archive),
        "type": "application/vnd.hmz.epic+gzip",
    }
    daemon = Daemon(runs_bundle=bundle)
    daemon.reading["r1"] = archive
    runs = Runs(_client(daemon))

    assert runs.bundle("e1") == Bundle("r1", "e1.hmzepic", len(archive), bundle["type"])
    out = runs.export("e1", tmp_path)

    assert out == Exported(tmp_path / "e1.hmzepic", "e1.hmzepic", len(archive))
    assert out.path.read_bytes() == archive
    assert [one["offset"] for one in daemon.asked("files.read")] == [0, CHUNK]
    assert daemon.closed == ["r1"]
    assert [one.name for one in tmp_path.iterdir()] == ["e1.hmzepic"]


def test_an_export_names_its_own_file_and_replaces_one_there(tmp_path: Path) -> None:
    daemon = Daemon(
        runs_bundle={"handle": "r1", "filename": "e1.hmzepic", "size": 3, "type": "t"}
    )
    daemon.reading["r1"] = b"new"
    to = tmp_path / "deep" / "mine.hmzepic"
    to.parent.mkdir()
    to.write_bytes(b"old")

    out = Runs(_client(daemon)).export("e1", to)

    assert (out.path, to.read_bytes()) == (to, b"new")


def test_an_export_into_a_directory_written_as_one_makes_it(tmp_path: Path) -> None:
    daemon = Daemon(
        runs_bundle={"handle": "r1", "filename": "e1.hmzepic", "size": 3, "type": "t"}
    )
    daemon.reading["r1"] = b"new"

    out = Runs(_client(daemon)).export("e1", f"{tmp_path}/kept/")

    assert out.path == tmp_path / "kept" / "e1.hmzepic"
    assert out.path.read_bytes() == b"new"


def test_a_download_that_is_refused_leaves_no_file_and_ends_the_handle(
    tmp_path: Path,
) -> None:
    client = mock.Mock(spec=["call"])
    client.call.side_effect = [Refused("There is no file r1.", code=404), {}]
    to = tmp_path / "e1.hmzepic"

    with pytest.raises(Refused, match="There is no file r1"):
        Files(client).download("r1", to)

    assert list(tmp_path.iterdir()) == []
    assert client.call.call_args.args == ("files.close", {"handle": "r1"})


def test_a_file_is_uploaded_a_chunk_at_a_time_and_imported(tmp_path: Path) -> None:
    archive = b"x" * (CHUNK + 7)
    at = tmp_path / "e1.hmzepic"
    at.write_bytes(archive)
    said = {
        "name": "e1",
        "workspace": "/w",
        "resumable": False,
        "why": "another machine",
    }
    daemon = Daemon(runs_import=said)

    got = Runs(_client(daemon)).import_(at, idem="k")

    assert got == Imported("e1", "/w", resumable=False, why="another machine")
    assert daemon.asked("files.create") == [{"name": "e1.hmzepic", "size": CHUNK + 7}]
    assert bytes(daemon.writing["w1"]) == archive
    assert [one["offset"] for one in daemon.asked("files.write")] == [0, CHUNK]
    assert daemon.asked("runs.import") == [{"handle": "w1", "idem": "k"}]
    # Taken by the import: not this side's to end.
    assert daemon.closed == []


def test_an_import_that_is_refused_ends_the_handle_it_sent(tmp_path: Path) -> None:
    at = tmp_path / "e1.hmzepic"
    at.write_bytes(b"not one")
    daemon = Daemon(runs_import=Refused("That is not a .hmzepic.", code=400))

    with pytest.raises(Refused, match="That is not a"):
        Runs(_client(daemon)).import_(at)

    assert daemon.closed == ["w1"]


def test_an_archive_on_the_daemons_machine_is_imported_by_its_path() -> None:
    said = {"name": "e1", "workspace": "/w", "resumable": True, "why": ""}
    daemon = Daemon(runs_import=said)

    got = Runs(_client(daemon)).imported(path="/srv/e1.hmzepic")

    assert got == Imported("e1", "/w", resumable=True, why="")
    assert daemon.asked("runs.import") == [{"path": "/srv/e1.hmzepic"}]


def test_a_backup_not_waited_for_says_only_what_was_queued() -> None:
    daemon = Daemon(runs_backup={"queued": ["lab", "home"]})

    went = Runs(_client(daemon)).backup("e1", to=["lab", "home"], idem="k")

    assert went == {"lab": {}, "home": {}}
    assert daemon.calls == [
        ("runs.backup", {"name": "e1", "to": ["lab", "home"], "idem": "k"})
    ]


def test_a_backup_waited_for_says_how_each_target_went(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", mock.Mock())
    old = {"at": "t0", "ok": True, "error": "", "why": "end"}
    new = {"at": "t1", "ok": True, "error": "", "why": "manual"}
    bad = {"at": "t2", "ok": False, "error": "rejected", "why": "manual"}
    # One its policy made meanwhile, which is not the one asked for.
    other = {"at": "t0.5", "ok": False, "error": "busy", "why": "interval"}
    daemon = Daemon(
        runs_backup={"queued": ["lab", "home"]},
        runs_get=[
            {"backed": {"lab": old}},
            {"backed": {"lab": other}},
            {"backed": {"lab": new}},
            {"backed": {"lab": new, "home": bad}},
        ],
    )

    went = Runs(_client(daemon)).backup("e1", wait=None)

    assert went == {"lab": new, "home": bad}
    assert daemon.asked("runs.backup") == [{"name": "e1"}]


def test_a_backup_that_is_not_done_in_time_says_which_target_was_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.sleep", mock.Mock())
    daemon = Daemon(runs_backup={"queued": ["lab"]}, runs_get={"backed": {}})

    with pytest.raises(TimeoutError, match="no backup of e1 to lab"):
        Runs(_client(daemon)).backup("e1", wait=0.01)


def test_the_targets_are_the_settings_own_with_the_defaults_marked() -> None:
    client = mock.Mock(spec=["call"])
    client.call.return_value = {
        "backup": {
            "targets": [
                {
                    "name": "lab",
                    "url": "https://***@host/e.git",
                    "branch": "main",
                    "policies": ["end"],
                    "every": 30,
                },
                {
                    "name": "home",
                    "url": "/srv/e",
                    "branch": "epics",
                    "policies": [],
                    "every": 5,
                },
            ],
            "defaults": ["home"],
        }
    }

    assert Backups(client).targets() == [
        Target("lab", "https://***@host/e.git", "main", ("end",), 30, default=False),
        Target("home", "/srv/e", "epics", (), 5, default=True),
    ]
    client.call.assert_called_once_with("settings.get", {})


def test_what_a_target_holds_is_listed_and_one_of_them_pulled() -> None:
    held: dict[str, Any] = {
        "key": "laptop/project/e1",
        "machine": "laptop",
        "workspace": "project",
        "epic": "e1",
        "flow": "ralph",
        "task": "fix it",
        "began": "b",
        "ended": "e",
        "how": "done",
        "head": "abc",
        "chat": False,
        "here": True,
    }
    client = mock.Mock(spec=["call"])
    client.call.side_effect = [{"epics": [held]}, {"name": "e1"}]
    backups = Backups(client)

    assert backups.epics("lab") == [Stored(**held)]
    assert backups.pull("lab", "laptop/project/e1", idem="k") == "e1"
    assert client.call.call_args_list == [
        mock.call("backups.epics", {"target": "lab"}, idem=None, seconds=None),
        mock.call(
            "backups.pull",
            {"target": "lab", "key": "laptop/project/e1"},
            idem="k",
            seconds=None,
        ),
    ]


def test_a_handle_is_written_read_and_closed_in_base64() -> None:
    client = mock.Mock(spec=["call"])
    client.call.side_effect = [
        {"handle": "w1"},
        {"size": 2},
        {"data": base64.b64encode(b"hi").decode(), "eof": True},
        {},
    ]
    files = Files(client)

    assert files.create("a.bin", 2) == "w1"
    assert files.write("w1", 0, b"hi") == 2
    assert files.read("r1", 0, 16) == Chunk(b"hi", eof=True)
    files.close("w1")

    assert [one.args for one in client.call.call_args_list] == [
        ("files.create", {"name": "a.bin", "size": 2}),
        ("files.write", {"handle": "w1", "offset": 0, "data": "aGk="}),
        ("files.read", {"handle": "r1", "offset": 0, "length": 16}),
        ("files.close", {"handle": "w1"}),
    ]
