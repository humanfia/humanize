"""`hmz daemon`: run, reach, pair and install this machine's daemon (Section 13 of cli.md)."""

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
import hmz.daemon.link
import hmz.daemon.routing
import hmz.reach
from hmz.cli.daemon import daemon
from hmz.rpc import RpcError


class _Peer:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        del timeout
        self.calls.append((method, params))
        said = self.answers[method]
        if isinstance(said, BaseException):
            raise said
        return said

    def close(self) -> None:
        pass


@pytest.fixture
def peer(monkeypatch: pytest.MonkeyPatch) -> _Peer:
    held = _Peer({})
    monkeypatch.setattr(hmz.daemon, "start", mock.Mock())

    def dialed(*_: object, **__: object) -> tuple[_Peer, dict[str, Any]]:
        return held, {}

    monkeypatch.setattr(hmz.daemon.link, "dialed", dialed)
    return held


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["nothing"],
        ["connect"],
        ["serve", "--listen", "unix:"],
        ["pair", "--route", "nowhere"],
        ["pair", "--seconds", "59"],
        ["devices", "revoke"],
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


def test_pair_writes_the_code_and_when_it_stops_admitting(
    peer: _Peer, capsys: pytest.CaptureFixture[str]
) -> None:
    peer.answers["pair.create"] = {"code": "hmz-pair:abc", "expires": 1_900_000_000}

    assert daemon(["pair", "--route", "tcp://h:1", "--seconds", "60"]) == 0

    said = capsys.readouterr()
    assert said.out == "hmz-pair:abc\n"
    assert said.err.startswith(
        "hmz daemon pair: claim this code on the device to pair before "
    )
    assert peer.calls == [("pair.create", {"seconds": 60, "routes": ["tcp://h:1"]})]


def test_devices_lists_each_paired_device(
    peer: _Peer, capsys: pytest.CaptureFixture[str]
) -> None:
    peer.answers["devices.list"] = {
        "devices": [
            {"name": "a", "fingerprint": "f", "added": "t1", "seen": None, "live": 0},
            {"name": "b", "fingerprint": "g", "added": "t2", "seen": "t3", "live": 1},
        ]
    }

    assert daemon(["devices"]) == 0
    assert capsys.readouterr().out == "a\tf\tt1\t\nb\tg\tt2\tt3\n"


def test_revoking_says_how_many_sessions_closed(
    peer: _Peer, capsys: pytest.CaptureFixture[str]
) -> None:
    peer.answers["devices.revoke"] = {"dropped": 2}

    assert daemon(["devices", "revoke", "laptop"]) == 0
    assert capsys.readouterr().out == (
        "hmz daemon devices: revoked laptop; 2 sessions closed\n"
    )


def test_a_refusal_is_said_in_its_own_words(
    peer: _Peer, capsys: pytest.CaptureFixture[str]
) -> None:
    peer.answers["devices.revoke"] = RpcError(400, "local cannot be revoked.")

    assert daemon(["devices", "revoke", "local"]) == 1
    assert capsys.readouterr().err == "hmz: local cannot be revoked.\n"


def test_a_daemon_that_cannot_be_reached_is_said_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(hmz.daemon, "start", mock.Mock(side_effect=OSError("no fork")))

    assert daemon(["pair"]) == 1
    assert capsys.readouterr().err == "hmz: the daemon cannot be reached: no fork\n"


def test_a_daemon_of_another_protocol_is_said_as_it_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    older = OSError(errno.EADDRINUSE, "the runs on this machine are held by an older")
    monkeypatch.setattr(hmz.daemon, "start", mock.Mock(side_effect=older))

    assert daemon(["devices"]) == 1
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


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    ran = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
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
    home: mock.Mock,
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
    assert home.call_args_list[-1].args[0][0] == command
    assert capsys.readouterr().out == f"hmz daemon: installed {tmp_path / at}\n"

    assert daemon(["uninstall"]) == 0
    assert not (tmp_path / at).exists()
    assert capsys.readouterr().out == f"hmz daemon: uninstalled {tmp_path / at}\n"
    assert daemon(["uninstall"]) == 1


def test_the_unit_goes_under_an_absolute_xdg_config_home(
    home: mock.Mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))

    assert daemon(["install"]) == 0
    assert (tmp_path / "cfg/systemd/user/hmz-daemon.service").exists()
    assert not (tmp_path / ".config").exists()


def test_a_relative_xdg_config_home_is_ignored(
    home: mock.Mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", "cfg")

    assert daemon(["install"]) == 0
    assert (tmp_path / ".config/systemd/user/hmz-daemon.service").exists()
    assert not (tmp_path / "cfg").exists()


@pytest.fixture
def released(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A unit a released hmz wrote under `~/.config`, enabled, with XDG_CONFIG_HOME elsewhere."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    unit = tmp_path / ".config/systemd/user/hmz-daemon.service"
    (unit.parent / "default.target.wants").mkdir(parents=True)
    unit.write_text("[Unit]\n")
    (unit.parent / "default.target.wants/hmz-daemon.service").symlink_to(unit)
    return unit


def test_install_replaces_the_unit_a_released_hmz_left(
    home: mock.Mock, tmp_path: Path, released: Path
) -> None:
    assert daemon(["install"]) == 0
    assert (tmp_path / "cfg/systemd/user/hmz-daemon.service").exists()
    assert not released.exists()
    assert not (
        released.parent / "default.target.wants/hmz-daemon.service"
    ).is_symlink()
    assert [call.args[0][2] for call in home.call_args_list] == [
        "daemon-reload",
        "enable",
        "daemon-reload",
    ]


def test_uninstall_removes_the_unit_a_released_hmz_left(
    home: mock.Mock,
    released: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert daemon(["uninstall"]) == 0
    assert not released.exists()
    assert home.call_args_list[0].args[0][2:] == [
        "disable",
        "--now",
        "hmz-daemon.service",
    ]
    assert capsys.readouterr().out == f"hmz daemon: uninstalled {released}\n"
    assert daemon(["uninstall"]) == 1


def test_a_released_unit_is_kept_while_the_install_fails(
    home: mock.Mock, released: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home.return_value = subprocess.CompletedProcess([], 1, "", "Failed to connect\n")

    assert daemon(["install"]) == 1
    assert released.exists()
    assert capsys.readouterr().err == "hmz: Failed to connect\n"


def test_install_runs_on_macos_and_linux_alone(
    home: mock.Mock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    assert daemon(["install"]) == 1
    assert capsys.readouterr().err == (
        "hmz: hmz daemon install runs on macOS and Linux alone\n"
    )
    home.assert_not_called()


def test_a_service_that_will_not_start_is_said_so(
    home: mock.Mock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    home.return_value = subprocess.CompletedProcess([], 1, "", "Failed to connect\n")

    assert daemon(["install"]) == 1
    assert capsys.readouterr().err == "hmz: Failed to connect\n"
