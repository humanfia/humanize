"""`hmz daemon`: run, reach and install this machine's daemon (Section 13 of cli.md)."""

from __future__ import annotations

import errno
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import hmz.daemon
import hmz.daemon.detaching
import hmz.daemon.routing
import hmz.reach
from hmz.cli.daemon import daemon


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["nothing"],
        ["connect"],
        ["serve", "--listen", "unix:"],
        ["pair"],
        ["devices"],
        ["install", "--now"],
    ],
)
def test_a_line_it_does_not_take_is_a_usage_error(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as ended:
        daemon(argv)
    assert ended.value.code == 2


def test_a_spec_that_is_not_a_listener_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        daemon(["serve", "--listen", "unix:"])
    assert "unix: is not a listener." in capsys.readouterr().err


def test_connect_says_the_sync_line_then_splices_its_streams_to_the_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`hmz-stdio/1` before any byte of the daemon's (Section 13.2.3)."""
    done = mock.Mock()
    socket, here = mock.Mock(), done.here
    monkeypatch.setattr(hmz.daemon, "start", mock.Mock())
    monkeypatch.setattr(hmz.reach, "dial", mock.Mock(return_value=socket))
    monkeypatch.setattr(hmz.reach, "stdio", mock.Mock(return_value=here))
    monkeypatch.setattr(hmz.reach, "splice", done.splice)
    assert daemon(["connect", "--stdio"]) == 0
    assert done.mock_calls == [
        mock.call.here.sendall(b"hmz-stdio/1\n"),
        mock.call.splice(here, socket),
    ]


def test_connect_that_reaches_no_daemon_says_nothing_on_standard_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.daemon, "start", mock.Mock())
    monkeypatch.setattr(
        hmz.reach, "dial", mock.Mock(side_effect=ConnectionRefusedError("refused"))
    )
    assert daemon(["connect", "--stdio"]) == 1
    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == "hmz: the daemon cannot be reached: refused\n"


def test_connect_to_a_daemon_of_another_protocol_says_how_it_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    older = OSError(errno.EADDRINUSE, "the runs on this machine are held by an older")
    monkeypatch.setattr(hmz.daemon, "start", mock.Mock())
    monkeypatch.setattr(hmz.reach, "dial", mock.Mock(side_effect=older))

    assert daemon(["connect", "--stdio"]) == 1
    assert capsys.readouterr().err == (
        "hmz: the runs on this machine are held by an older\n"
    )


@pytest.fixture
def settled(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    held = mock.Mock()
    monkeypatch.setattr(hmz.daemon.detaching, "settles", held)
    return held


@pytest.mark.usefixtures("settled")
def test_serve_says_a_daemon_is_already_running(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        hmz.daemon.routing,
        "serves",
        mock.Mock(side_effect=BlockingIOError(errno.EAGAIN, "locked")),
    )
    monkeypatch.setattr(hmz.daemon.where, "held", mock.Mock(return_value={"pid": 77}))
    monkeypatch.setattr("signal.signal", mock.Mock())

    assert daemon(["serve"]) == 1
    assert capsys.readouterr().err == "hmz: a daemon is already running (pid 77)\n"


def test_serve_says_each_route_it_listens_on(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    settled: mock.Mock,
) -> None:
    def serves(**said: Any) -> None:
        # The environment every host takes is settled before the daemon serves.
        settled.assert_called_once_with()
        assert said["listen"] == ["tcp://127.0.0.1:0"]
        assert said["kept"] is True
        said["opened"]("tcp://127.0.0.1:4100")

    monkeypatch.setattr(hmz.daemon.routing, "serves", serves)
    monkeypatch.setattr("signal.signal", mock.Mock())

    assert daemon(["serve", "--listen", "tcp://127.0.0.1:0"]) == 0
    assert capsys.readouterr().out == "hmz daemon: listening on tcp://127.0.0.1:4100\n"


class _Systemd:
    """`subprocess.run` as systemctl and launchctl answer it.

    `environment` is what the user's systemd manager shows (`None` where it cannot be asked),
    `failed` what every other command fails with, if anything.
    """

    def __init__(self) -> None:
        self.environment: str | None = ""
        self.failed = ""
        self.calls: list[list[str]] = []

    def __call__(self, step: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(step)
        if step[-1] == "show-environment":
            if self.environment is None:
                return subprocess.CompletedProcess(step, 1, "", "Failed to connect\n")
            return subprocess.CompletedProcess(step, 0, self.environment, "")
        return subprocess.CompletedProcess(
            step, int(bool(self.failed)), "", self.failed
        )

    def ran(self) -> list[list[str]]:
        """What ran but asking the manager its environment."""
        return [step for step in self.calls if step[-1] != "show-environment"]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Systemd:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    ran = _Systemd()
    monkeypatch.setattr(subprocess, "run", ran)
    return ran


@pytest.mark.parametrize(
    ("platform", "at", "command"),
    [
        ("darwin", "Library/LaunchAgents/ai.humanfia.hmz.daemon.plist", "launchctl"),
        ("linux", ".config/systemd/user/hmz-daemon.service", "systemctl"),
    ],
)
def test_install_writes_the_service_and_uninstall_removes_it(
    home: _Systemd,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    platform: str,
    at: str,
    command: str,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)

    assert daemon(["install"]) == 0
    written = (tmp_path / at).read_text()
    assert "daemon" in written
    assert "serve" in written
    assert home.ran()[-1][0] == command
    assert capsys.readouterr().out == f"hmz daemon: installed {tmp_path / at}\n"

    assert daemon(["uninstall"]) == 0
    assert not (tmp_path / at).exists()
    assert capsys.readouterr().out == f"hmz daemon: uninstalled {tmp_path / at}\n"
    assert daemon(["uninstall"]) == 1


def test_the_unit_goes_under_the_xdg_config_home_systemd_has(
    home: _Systemd, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    # The shell's own is not where systemd looks.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "shell"))
    home.environment = f"HOME={tmp_path}\nXDG_CONFIG_HOME={tmp_path / 'cfg'}\n"

    assert daemon(["install"]) == 0
    assert (tmp_path / "cfg/systemd/user/hmz-daemon.service").exists()
    assert not (tmp_path / ".config").exists()
    assert not (tmp_path / "shell").exists()


@pytest.mark.parametrize(
    "environment",
    [None, "HOME=/home/u\n", "XDG_CONFIG_HOME=cfg\n"],
    ids=["unasked", "unset", "relative"],
)
def test_the_unit_goes_under_dot_config_where_systemd_has_no_absolute_xdg_config_home(
    home: _Systemd,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "shell"))
    home.environment = environment

    assert daemon(["install"]) == 0
    assert (tmp_path / ".config/systemd/user/hmz-daemon.service").exists()
    assert not (tmp_path / "cfg").exists()
    assert not (tmp_path / "shell").exists()


@pytest.fixture
def released(home: _Systemd, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A unit a released hmz wrote under `~/.config`, enabled, with XDG_CONFIG_HOME elsewhere."""
    monkeypatch.setattr(sys, "platform", "linux")
    home.environment = f"XDG_CONFIG_HOME={tmp_path / 'cfg'}\n"
    unit = tmp_path / ".config/systemd/user/hmz-daemon.service"
    (unit.parent / "default.target.wants").mkdir(parents=True)
    unit.write_text("[Unit]\n")
    (unit.parent / "default.target.wants/hmz-daemon.service").symlink_to(unit)
    return unit


def test_install_replaces_the_unit_a_released_hmz_left(
    home: _Systemd, tmp_path: Path, released: Path
) -> None:
    assert daemon(["install"]) == 0
    assert (tmp_path / "cfg/systemd/user/hmz-daemon.service").exists()
    assert not released.exists()
    assert not (
        released.parent / "default.target.wants/hmz-daemon.service"
    ).is_symlink()
    assert [step[2] for step in home.ran()] == [
        "daemon-reload",
        "enable",
        "daemon-reload",
    ]


def test_uninstall_removes_the_unit_a_released_hmz_left(
    home: _Systemd,
    released: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert daemon(["uninstall"]) == 0
    assert not released.exists()
    assert home.ran()[0][2:] == [
        "disable",
        "--now",
        "hmz-daemon.service",
    ]
    assert capsys.readouterr().out == f"hmz daemon: uninstalled {released}\n"
    assert daemon(["uninstall"]) == 1


def test_a_released_unit_is_kept_while_the_install_fails(
    home: _Systemd, released: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home.failed = "Failed to connect\n"

    assert daemon(["install"]) == 1
    assert released.exists()
    assert capsys.readouterr().err == "hmz: Failed to connect\n"


def test_install_runs_on_macos_and_linux_alone(
    home: _Systemd, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    assert daemon(["install"]) == 1
    assert capsys.readouterr().err == (
        "hmz: hmz daemon install runs on macOS and Linux alone\n"
    )
    assert not home.calls


def test_a_service_that_will_not_start_is_said_so(
    home: _Systemd, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    home.failed = "Failed to connect\n"

    assert daemon(["install"]) == 1
    assert capsys.readouterr().err == "hmz: Failed to connect\n"
