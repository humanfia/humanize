"""`hmz settings`: the settings read, each one written, and a workspace's set-up forgotten."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from hmz.cli import main, tree

SAID: dict[str, Any] = {
    "workspace": "/home/me",
    "flow": "",
    "chat": "claude/opus:auto",
    "prefer": "native",
    "ai_chan": "",
    "details": False,
    "harness_sessions": False,
    "reports": None,
    "flows": ["ralph"],
    "backup": {
        "targets": [
            {
                "name": "lab",
                "url": "https://***@example.org/epics.git",
                "branch": "main",
                "policies": ["session"],
                "every": 30,
            }
        ],
        "defaults": ["lab"],
    },
    "listen": [],
    "ice_servers": [],
}


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The settings family of the client the command reaches."""
    client = mock.Mock()
    monkeypatch.setattr(tree, "reach", mock.Mock(return_value=client))
    for method in (client.settings.get, client.settings.set):
        method.return_value = mock.Mock(said=SAID, forgot=None)
    return client.settings


def test_every_setting_is_printed_a_line_each(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["settings", "get"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "workspace         /home/me"
    assert 'flows             ["ralph"]' in lines
    assert "reports           null" in lines
    assert "details           false" in lines
    settings.get.assert_called_once_with(None)

    assert main(["settings", "get", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == SAID


def test_one_setting_is_printed_alone(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["settings", "get", "chat", "-w", "~/project"]) == 0
    assert capsys.readouterr().out == "claude/opus:auto\n"
    settings.get.assert_called_once_with("~/project")

    assert main(["settings", "get", "backup", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"backup": SAID["backup"]}


def test_a_relative_workspace_is_read_from_this_directory(
    settings: mock.Mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["settings", "get", "-w", "project"]) == 0

    settings.get.assert_called_once_with(str(Path.cwd() / "project"))


def test_a_setting_there_is_none_of_is_a_usage_error(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["settings", "get", "nope"]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == (
        "hmz settings get: no setting named nope\n"
        "Run `hmz settings get --help` for help.\n"
    )
    settings.get.assert_not_called()


@pytest.mark.parametrize(
    ("line", "written"),
    [
        (["details", "on"], {"details": True}),
        (["details", "false"], {"details": False}),
        (["reports", "off"], {"reports": False}),
        (["harness_sessions", "true"], {"harness_sessions": True}),
        (["chat", "codex/sol"], {"workspace": None, "chat": "codex/sol"}),
        (
            ["chat", "codex/sol", "-w", "~/project"],
            {"workspace": "~/project", "chat": "codex/sol"},
        ),
        (["prefer", "flow"], {"prefer": "flow"}),
        (
            ["listen", "tcp://0.0.0.0:7000", "ws://0.0.0.0:7001"],
            {"listen": ["tcp://0.0.0.0:7000", "ws://0.0.0.0:7001"]},
        ),
        (["listen", '["tcp://0.0.0.0:7000"]'], {"listen": ["tcp://0.0.0.0:7000"]}),
        (["listen"], {"listen": []}),
        (["listen", "{odd", "tcp://h:1"], {"listen": ["{odd", "tcp://h:1"]}),
        (
            ["ice_servers", "stun:s:1", '{"urls": "turn:t:1", "credential": true}'],
            {
                "ice_servers": [
                    {"urls": "stun:s:1"},
                    {"urls": "turn:t:1", "credential": True},
                ]
            },
        ),
        (
            ["backup", '{"targets": [], "defaults": []}'],
            {"backup": {"targets": [], "defaults": []}},
        ),
    ],
)
def test_one_setting_is_written_and_said_saved(
    settings: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    line: list[str],
    written: dict[str, Any],
) -> None:
    assert main(["settings", "set", *line]) == 0

    assert capsys.readouterr().out == "Saved.\n"
    settings.set.assert_called_once_with(**written)

    assert main(["settings", "set", *line, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == SAID


def test_servers_with_a_credential_are_read_from_standard_input(
    settings: mock.Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    servers = [{"urls": "turn:t:1", "username": "u", "credential": "hush"}]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(servers)))

    assert main(["settings", "set", "ice_servers", "-"]) == 0

    settings.set.assert_called_once_with(ice_servers=servers)


def test_a_credential_on_the_line_is_refused_and_never_said_back(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    server = '{"urls": "turn:t:1", "username": "u", "credential": "hush-hush"}'

    assert main(["settings", "set", "ice_servers", server]) == 2

    said = capsys.readouterr()
    assert said.err.splitlines()[0] == (
        "hmz settings set ice_servers: a credential is read from standard input only: "
        "give the servers as JSON with `-`"
    )
    assert "hush-hush" not in said.out + said.err
    settings.set.assert_not_called()


def test_removing_a_backup_target_there_is_none_of_writes_nothing(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["settings", "set", "backup.target", "lba", "--remove"]) == 2

    assert capsys.readouterr().err.splitlines()[0] == (
        "hmz settings set backup.target: no backup target named lba"
    )
    settings.set.assert_not_called()


def test_a_backup_target_changed_keeps_its_place_among_the_defaults(
    settings: mock.Mock,
) -> None:
    kept = settings.get.return_value.said
    backup = kept["backup"] | {"defaults": ["lab", "offsite"]}
    settings.get.return_value = mock.Mock(said=kept | {"backup": backup})

    assert main(["settings", "set", "backup.target", "lab", "--branch", "dev"]) == 0

    assert _backup(settings)["defaults"] == ["lab", "offsite"]


@pytest.mark.parametrize(
    "line",
    [
        ["backup", "{nope"],
        ["listen", "[nope"],
        ["ice_servers", "{nope"],
        ["ice_servers", "[1]"],
    ],
)
def test_a_value_that_is_not_json_is_a_usage_error_and_nothing_is_written(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str], line: list[str]
) -> None:
    assert main(["settings", "set", *line]) == 2

    said = capsys.readouterr()
    assert said.out == ""
    assert said.err.splitlines()[0] == (
        f"hmz settings set {line[0]}: This is not valid JSON."
    )
    settings.set.assert_not_called()


def test_a_switch_takes_on_or_off_only(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as left:
        main(["settings", "set", "details", "maybe"])

    assert left.value.code == 2
    assert "invalid choice: 'maybe'" in capsys.readouterr().err
    settings.set.assert_not_called()


def _backup(settings: mock.Mock) -> dict[str, Any]:
    """The backup the last `settings.set` wrote."""
    (_, written) = settings.set.call_args
    assert set(written) == {"backup"}
    return written["backup"]


def test_a_backup_target_is_added_beside_the_ones_there(settings: mock.Mock) -> None:
    line = ["settings", "set", "backup.target", "home"]
    more = ["--url", "git@host:me/epics.git", "--policy", "end", "--policy", "session"]

    assert main([*line, *more, "--every", "5", "--default"]) == 0

    assert _backup(settings) == {
        "targets": [
            *SAID["backup"]["targets"],
            {
                "name": "home",
                "url": "git@host:me/epics.git",
                "branch": "main",
                "policies": ["session", "end"],
                "every": 5,
            },
        ],
        "defaults": ["lab", "home"],
    }


def test_a_backup_target_changed_keeps_what_was_not_said(settings: mock.Mock) -> None:
    line = ["settings", "set", "backup.target", "lab"]

    assert main([*line, "--branch", "epics", "--policy", "manual"]) == 0

    assert _backup(settings) == {
        "targets": [
            {
                "name": "lab",
                # As it was shown, which the daemon reads as the URL it has written.
                "url": "https://***@example.org/epics.git",
                "branch": "epics",
                "policies": [],
                "every": 30,
            }
        ],
        "defaults": ["lab"],
    }

    assert main([*line, "--no-default"]) == 0
    assert _backup(settings)["defaults"] == []


def test_a_backup_target_is_removed_from_the_defaults_too(settings: mock.Mock) -> None:
    assert main(["settings", "set", "backup.target", "lab", "--remove"]) == 0

    assert _backup(settings) == {"targets": [], "defaults": []}


def test_the_default_targets_are_written_whole(settings: mock.Mock) -> None:
    assert main(["settings", "set", "backup.defaults"]) == 0
    assert _backup(settings) == {
        "targets": SAID["backup"]["targets"],
        "defaults": [],
    }

    assert main(["settings", "set", "backup.defaults", "lab", "home"]) == 0
    assert _backup(settings)["defaults"] == ["lab", "home"]


def test_forgetting_says_whether_there_was_anything(
    settings: mock.Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    settings.forget.return_value = mock.Mock(said={**SAID, "forgot": True}, forgot=True)

    assert main(["settings", "forget", "-w", "~/project"]) == 0
    assert capsys.readouterr().out == "Forgotten.\n"
    settings.forget.assert_called_once_with("~/project")

    settings.forget.return_value = mock.Mock(
        said={**SAID, "forgot": False}, forgot=False
    )
    assert main(["settings", "forget", "-w", "~/project"]) == 0
    assert capsys.readouterr().out == "Nothing to forget.\n"

    assert main(["settings", "forget", "-w", "~/project", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {**SAID, "forgot": False}
