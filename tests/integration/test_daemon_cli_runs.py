"""`hmz runs` and `hmz backup`, asked of a real daemon over its socket, and the SDK the same.

An epic written down in the test's own workspace is listed, read back, laid out, exported to
a file and imported from it, backed up to a bare git repository in the test's own directory,
found there, and pulled back down once this machine no longer holds it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import tomlkit

from hmz import cli, config
from hmz.runtime.epic import Epic
from hmz.sdk import Client, Refused
from tests.integration.doubles_daemon import hosting, project

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.timeout(120)]


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A workspace with one epic written down in it, and a daemon taken down after."""
    at = project(tmp_path, monkeypatch)
    with Epic("ralph", "fix the parser\nand its tests", at):
        pass
    with hosting():
        yield at


@pytest.fixture
def bare(tmp_path: Path) -> Path:
    """A backup target `t`, which is also the default: a bare repository of the test's own."""
    at = tmp_path / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", str(at)], check=True)
    config().mkdir(parents=True, exist_ok=True)
    (config() / "settings.toml").write_text(
        tomlkit.dumps(
            {"backup": {"targets": [{"name": "t", "url": str(at)}], "defaults": ["t"]}}
        )
    )
    return at


def _json(capsys: pytest.CaptureFixture[str], *line: str) -> Any:
    """What a command answered under `--json`, having done what it was asked."""
    assert cli.main([*line, "--json"]) == 0, capsys.readouterr().err
    said = capsys.readouterr()
    assert said.err == ""
    return json.loads(said.out)


def _text(capsys: pytest.CaptureFixture[str], *line: str) -> str:
    assert cli.main(list(line)) == 0, capsys.readouterr().err
    return capsys.readouterr().out


def _refused(capsys: pytest.CaptureFixture[str], *line: str) -> str:
    assert cli.main(list(line)) == 1
    return capsys.readouterr().err


def test_an_epic_is_listed_filtered_and_read_back(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    listed = _json(capsys, "runs", "list")
    (row,) = listed["runs"]
    name = row["name"]
    assert (row["flow"], row["task"], row["how"]) == ("ralph", "fix the parser", "done")
    assert (listed["total"], listed["counts"], listed["flows"]) == (
        1,
        {"done": 1},
        ["ralph"],
    )

    began = row["began"]
    assert _text(capsys, "runs", "list", "--workspace", ".", "-q", "PARSER") == (
        f"{name}  done  ralph  {began}  fix the parser\n"
    )
    assert _text(capsys, "runs", "list", "--status", "failed") == ""
    assert _json(capsys, "runs", "list", "--flow", "another")["total"] == 0
    elsewhere = str(workspace.parent)
    assert _json(capsys, "runs", "list", "--workspace", elsewhere)["runs"] == []

    one = _json(capsys, "runs", "show", name)
    assert (one["name"], one["task"], one["calls"]) == (
        name,
        "fix the parser\nand its tests",
        [],
    )
    shown = _text(capsys, "runs", "show", name)
    assert f"name                 {name}\n" in shown
    assert shown.endswith("task\n  fix the parser\n  and its tests\n")

    assert _refused(capsys, "runs", "show", "nothing") == (
        "hmz runs show: There is no epic nothing.\n"
    )


def test_an_epic_is_traced_laid_out_and_a_span_of_it_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    name = _json(capsys, "runs", "list")["runs"][0]["name"]

    assert _json(capsys, "runs", "trace", name) == {"sessions": []}
    assert _text(capsys, "runs", "trace", name) == ""

    laid = _json(capsys, "runs", "timeline", name)
    assert (laid["epic"], laid["live"], laid["summary"]["spans"]) == (name, False, 1)
    drawn = _text(capsys, "runs", "timeline", name, "--spans").splitlines()
    # A process, its one track, and that track's one span: how long each took is the run's.
    process, track, only = (line.split() for line in drawn)
    assert process[:5] == ["0", "flow", "ralph", "done", "0.000"]
    assert (drawn[1], track) == ("  flows  1 span", ["flows", "1", "span"])
    assert (only[:2], only[3:]) == (["0", "0.000"], ["flow", "ralph"])
    assert _text(capsys, "runs", "timeline", name).splitlines() == drawn[:2]

    span = _json(capsys, "runs", "span", name, "0", "--layout", laid["layout"])
    assert (span["id"], span["cat"], span["name"]) == (0, "flow", "ralph")
    assert _json(capsys, "runs", "span", name, "0") == span
    assert _text(capsys, "runs", "span", name, "0").startswith("id       0\n")
    assert _refused(capsys, "runs", "span", name, "7") == (
        f"hmz runs span: Epic {name} has no span 7.\n"
    )
    assert _refused(capsys, "runs", "span", name, "0", "--layout", "stale") == (
        f"hmz runs span: Epic {name} has been laid out again; read it again.\n"
    )


def test_what_epics_spent_is_totalled_by_flow_and_by_day(
    capsys: pytest.CaptureFixture[str],
) -> None:
    said = _json(capsys, "runs", "usage", "--days", "2", "--workspace", ".")

    assert (said["days_back"], len(said["days"]), said["ended"]) == (2, 2, {"done": 1})
    assert [(one["flow"], one["runs"]) for one in said["flows"]] == [("ralph", 1)]
    assert said["whole"]["runs"] == 1
    lines = _text(capsys, "runs", "usage").splitlines()
    assert lines[0].split() == [
        "Flow",
        "Epics",
        "Cost",
        "Output",
        "tokens",
        "Time",
        "working",
    ]
    assert lines[1].split()[:2] == ["ralph", "1"]
    assert lines[-1].split()[:2] == ["Total", "1"]


def test_an_epic_is_exported_to_a_file_and_imported_from_it(
    tmp_path: Path, workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    one = _json(
        capsys, "runs", "show", _json(capsys, "runs", "list")["runs"][0]["name"]
    )
    name = one["name"]

    assert _text(capsys, "runs", "export", name) == f"{workspace / name}.hmzepic\n"
    out = _json(capsys, "runs", "export", name, "-o", str(tmp_path))
    archive = tmp_path / f"{name}.hmzepic"
    assert out == {
        "path": str(archive),
        "filename": archive.name,
        "size": archive.stat().st_size,
    }
    assert archive.read_bytes()[:2] == b"\x1f\x8b"

    assert "is already here" in _refused(capsys, "runs", "import", str(archive))
    shutil.rmtree(one["at"])
    assert _json(capsys, "runs", "list")["total"] == 0

    assert _json(capsys, "runs", "import", str(archive)) == {
        "name": name,
        "workspace": str(workspace.resolve()),
        "resumable": False,
        "why": "",
    }
    assert _json(capsys, "runs", "show", name)["task"] == one["task"]

    shutil.rmtree(one["at"])
    assert (
        _text(capsys, "runs", "import", str(archive), "--there") == f"Imported {name}\n"
    )
    assert _refused(capsys, "runs", "import", "relative.hmzepic", "--there") == (
        "hmz runs import: Say path as a whole path on this machine.\n"
    )
    assert "No such file" in _refused(capsys, "runs", "import", "gone.hmzepic")


def test_an_epic_is_backed_up_found_in_its_target_and_pulled_back_down(
    bare: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    name = _json(capsys, "runs", "list")["runs"][0]["name"]

    assert _json(capsys, "backup", "list") == {
        "targets": [
            {
                "name": "t",
                "url": str(bare),
                "branch": "main",
                "policies": [],
                "every": 30,
            }
        ],
        "defaults": ["t"],
    }
    assert _text(capsys, "backup", "list") == f"t  {bare}  main    default\n"
    assert _json(capsys, "backup", "list", "--target", "t") == {"epics": []}

    went = _json(capsys, "backup", "run", name)
    assert went["queued"] == ["t"]
    assert (went["backed"]["t"]["ok"], went["backed"]["t"]["error"]) == (True, "")
    assert _json(capsys, "runs", "show", name)["backed"] == went["backed"]
    assert _text(capsys, "backup", "run", name, "--to", "t").startswith(
        "t: uploaded 20"
    )
    assert _refused(capsys, "backup", "run", name, "--to", "nowhere").startswith(
        "hmz backup run: "
    )

    (held,) = _json(capsys, "backup", "list", "--target", "t")["epics"]
    assert (held["epic"], held["flow"], held["how"], held["chat"], held["here"]) == (
        name,
        "ralph",
        "done",
        False,
        True,
    )
    assert _text(capsys, "backup", "list", "--target", "t") == (
        f"{held['key']}  done  ralph  here  fix the parser and its tests\n"
    )
    assert "already here" in _refused(capsys, "backup", "pull", name, "--target", "t")
    assert _refused(capsys, "backup", "pull", "nothing", "--target", "t") == (
        "hmz backup pull: t holds no epic or chat nothing.\n"
    )

    shutil.rmtree(_json(capsys, "runs", "show", name)["at"])
    assert _json(capsys, "backup", "list", "--target", "t")["epics"][0]["here"] is False
    assert _text(capsys, "backup", "pull", name, "--target", "t") == f"{name}\n"
    assert _json(capsys, "runs", "list")["runs"][0]["name"] == name


def test_a_backup_with_no_target_to_go_to_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    name = _json(capsys, "runs", "list")["runs"][0]["name"]

    assert _refused(capsys, "backup", "run", name) == (
        "hmz backup run: There is no backup target: add one in Settings.\n"
    )
    assert cli.main(["backup", "list"]) == 0
    said = capsys.readouterr()
    assert (said.out, said.err) == ("", "No backup target.\n")
    assert cli.main(["backup", "list", "--target", "t"]) == 1


def test_the_same_is_asked_through_the_sdk(bare: Path, tmp_path: Path) -> None:
    with Client.local() as client:
        found = client.runs.list(query="parser", limit=5)
        (row,) = found.runs
        name = row["name"]
        assert (found.total, found.limit, found.flows) == (1, 5, ["ralph"])
        one = client.runs.get(name)
        assert one["task"] == "fix the parser\nand its tests"
        assert client.runs.trace(name) == []
        laid = client.runs.timeline(name)
        assert client.runs.span(name, 0)["name"] == "ralph"
        assert client.runs.span(name, 0, laid["layout"])["id"] == 0
        assert client.runs.usage(days=1)["whole"]["runs"] == 1

        out = client.runs.export(name, tmp_path / "kept" / "mine.hmzepic")
        assert out.path == tmp_path / "kept" / "mine.hmzepic"
        assert out.size == out.path.stat().st_size > 0
        with pytest.raises(Refused, match="is already here") as refused:
            client.runs.import_(out.path)
        assert (refused.value.code, refused.value.data) == (409, {"name": name})

        (target,) = client.backups.targets()
        assert (target.name, target.url, target.default) == ("t", str(bare), True)
        went = client.runs.backup(name, wait=60)
        assert went["t"]["ok"] is True
        again = client.runs.backup(name, to=["t"], wait=60)
        assert again["t"]["at"] > went["t"]["at"]
        (held,) = client.backups.epics("t")
        assert (held.epic, held.flow, held.chat, held.here) == (
            name,
            "ralph",
            False,
            True,
        )

        shutil.rmtree(Path(one["at"]))
        assert client.backups.pull("t", held.key) == name
        shutil.rmtree(Path(one["at"]))
        got = client.runs.import_(out.path)
        assert (got.name, got.resumable) == (name, False)

        # A handle of this session's own, filled and read by nobody, is ended by hand.
        handle = client.files.upload(out.path)
        client.files.close(handle)
        with pytest.raises(Refused, match="There is no file") as gone:
            client.files.close(handle)
        assert gone.value.code == 404
