"""`hmz hosts`: a daemon's hosts listed, one opened, its frontends let go, one closed."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from hmz.cli import main, tree

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def hosts(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The hosts family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    return client.hosts


def _held(**said: Any) -> mock.Mock:
    return mock.Mock(**said)


def _two(hosts: mock.Mock) -> None:
    hosts.list.return_value = [
        _held(pid=7, workspace="/w", started="2026-01-01", slot=""),
        _held(pid=8, workspace="/w", started="2026-01-02", slot="exec:ab"),
    ]
    hosts.running.return_value = [
        _held(
            workspace="/w",
            slot="exec:ab",
            state="running",
            kind="flow",
            flow="goal",
            epic="e1",
            chat="",
            task="win",
            asking=("1:q1",),
        )
    ]


def test_every_host_is_listed_with_what_it_runs(
    hosts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    _two(hosts)

    assert main(["hosts", "list"]) == 0
    assert capsys.readouterr().out == (
        "/w           idle\n/w  exec:ab  running  goal  win\n"
    )

    assert main(["hosts", "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)["hosts"]
    assert listed[0] == {
        "workspace": "/w",
        "slot": "",
        "pid": 7,
        "started": "2026-01-01",
        "state": "idle",
        "kind": "",
        "flow": "",
        "epic": "",
        "chat": "",
        "task": "",
        "asking": [],
    }
    assert (listed[1]["state"], listed[1]["asking"]) == ("running", ["1:q1"])


def test_only_the_hosts_running_something_are_listed_where_asked(
    hosts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    _two(hosts)

    assert main(["hosts", "list", "--running"]) == 0

    assert capsys.readouterr().out == "/w  exec:ab  running  goal  win\n"


def test_a_host_is_closed_by_its_workspace_and_slot(
    hosts: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["hosts", "stop"]) == 0
    assert capsys.readouterr().out == "Host closed.\n"
    (workspace, slot), _ = hosts.stop.call_args
    assert (workspace, slot) == (str(tmp_path.resolve()), "")

    assert main(["hosts", "stop", "-w", "/w", "--slot", "exec:ab", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"workspace": "/w", "slot": "exec:ab"}
    hosts.stop.assert_called_with("/w", "exec:ab")


def test_a_host_is_opened_without_attaching_and_its_slot_said(
    hosts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    hosts.open.return_value = {
        "pid": 41,
        "workspace": "/w",
        "started": "2026-01-01T00:00:00Z",
        "kind": "host",
        "protocol": "7",
        "slot": "exec:ab",
        "more": "not said",
    }

    assert main(["hosts", "open", "-w", "/w", "--slot", "exec:"]) == 0
    assert capsys.readouterr().out == "41  /w  exec:ab\n"
    hosts.open.assert_called_once_with("/w", "exec:")

    assert main(["hosts", "open", "-w", "/w", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "pid": 41,
        "workspace": "/w",
        "started": "2026-01-01T00:00:00Z",
        "kind": "host",
        "protocol": "7",
        "slot": "exec:ab",
    }
    hosts.open.assert_called_with("/w", "")


def test_every_frontend_of_a_host_is_let_go_and_counted(
    hosts: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    hosts.detach.return_value = 1

    assert main(["hosts", "detach", "-w", "/w"]) == 0
    assert capsys.readouterr().out == "1 frontend let go.\n"
    hosts.detach.assert_called_once_with("/w", "")

    hosts.detach.return_value = 3
    assert main(["hosts", "detach", "-w", "/w", "--slot", "chat:1f", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "workspace": "/w",
        "slot": "chat:1f",
        "let_go": 3,
    }
