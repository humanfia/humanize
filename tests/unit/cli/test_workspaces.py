"""`hmz workspaces`: the workspaces listed, added and forgotten, and a folder picked."""

from __future__ import annotations

import json
from types import SimpleNamespace as Said
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from hmz.cli import main, tree

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> mock.Mock:
    """The client the command reaches, asked from a directory."""
    reached = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=reached))
    monkeypatch.chdir(tmp_path)
    return reached


def _workspace(path: str, **said: Any) -> Said:
    held: dict[str, Any] = {
        "epics": 0,
        "chats": 0,
        "last": "",
        "running": False,
        "there": True,
    }
    return Said(path=path, **(held | said))


def test_the_workspaces_are_listed_with_how_each_stands(
    client: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client.workspaces.list.return_value = Said(
        workspaces=(
            _workspace("/here"),
            _workspace("/going", epics=12, chats=3, last="2026-01-02", running=True),
            _workspace("/gone", epics=1, last="2026-01-01", running=True, there=False),
        ),
        answer={"here": "/here", "workspaces": []},
    )

    assert main(["workspaces", "list"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "/here   0   0  -",
        "/going  12  3  2026-01-02  running",
        "/gone   1   0  2026-01-01  running, missing",
    ]
    client.workspaces.list.assert_called_once_with(str(tmp_path))

    assert main(["workspaces", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"here": "/here", "workspaces": []}


def test_no_workspace_is_said_beside_the_empty_list(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.workspaces.list.return_value = Said(workspaces=(), answer={})

    assert main(["workspaces", "list"]) == 0

    said = capsys.readouterr()
    assert (said.out, said.err) == ("", "No folders\n")


def test_a_folder_is_added_from_here_and_its_whole_path_printed(
    client: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client.workspaces.add.return_value = Said(
        kept="/whole/app", answer={"kept": "/whole/app"}
    )

    assert main(["workspaces", "add", "app"]) == 0
    assert capsys.readouterr().out == "/whole/app\n"
    client.workspaces.add.assert_called_once_with(str(tmp_path / "app"), str(tmp_path))

    assert main(["workspaces", "add", "~/app", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"kept": "/whole/app"}
    client.workspaces.add.assert_called_with("~/app", str(tmp_path))


def test_a_workspace_is_forgotten(
    client: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client.workspaces.forget.return_value = Said(answer={"here": "", "workspaces": []})

    assert main(["workspaces", "forget", "/old"]) == 0
    assert capsys.readouterr().out == "Forgotten\n"
    client.workspaces.forget.assert_called_once_with("/old", str(tmp_path))

    assert main(["workspaces", "forget", "/old", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"here": "", "workspaces": []}


def test_a_directory_is_browsed_a_whole_path_a_line(
    client: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client.paths.list.return_value = Said(
        whole="/home/me",
        entries=(Said(name="code", dir=True), Said(name="notes.txt", dir=False)),
        more=2,
        answer={"at": "~"},
    )

    assert main(["workspaces", "browse"]) == 0

    said = capsys.readouterr()
    assert said.out == "/home/me/code/\n/home/me/notes.txt\n"
    assert said.err == "2 more\n"
    client.paths.list.assert_called_once_with("~", files=None, hidden=None, env=None)

    assert main(["workspaces", "browse", "sub", "--files", "--hidden", "--json"]) == 0

    said = capsys.readouterr()
    assert json.loads(said.out) == {"at": "~"}
    assert said.err == ""
    client.paths.list.assert_called_with(
        str(tmp_path / "sub"), files=True, hidden=True, env=None
    )


def test_a_directory_of_a_runtimes_machine_is_named_as_it_was_written(
    client: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    client.paths.list.return_value = Said(
        whole="/", entries=(Said(name="srv", dir=True),), more=0, answer={}
    )

    assert main(["workspaces", "browse", "srv", "--env", "ssh@box"]) == 0

    said = capsys.readouterr()
    assert (said.out, said.err) == ("/srv/\n", "")
    client.paths.list.assert_called_once_with(
        "srv", files=None, hidden=None, env="ssh@box"
    )


def test_a_typed_path_is_completed_a_folder_a_line(
    client: mock.Mock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    client.paths.complete.return_value = ["~/code/", "~/cold/"]

    assert main(["workspaces", "complete", "~/co"]) == 0
    assert capsys.readouterr().out == "~/code/\n~/cold/\n"
    client.paths.complete.assert_called_once_with("~/co")

    assert main(["workspaces", "complete", "co"]) == 0
    client.paths.complete.assert_called_with(f"{tmp_path}/co")
    capsys.readouterr()

    assert main(["workspaces", "complete", "~/co", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"paths": ["~/code/", "~/cold/"]}
