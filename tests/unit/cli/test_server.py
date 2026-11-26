"""`hmz server`: the web interface's per-user login service."""

from __future__ import annotations

import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.cli import server

if TYPE_CHECKING:
    from collections.abc import Mapping


def _commands(
    monkeypatch: pytest.MonkeyPatch,
    answers: Mapping[tuple[str, ...], str] | None = None,
) -> list[list[str]]:
    called: list[list[str]] = []

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        called.append(arguments)
        return subprocess.CompletedProcess(
            arguments, 0, (answers or {}).get(tuple(arguments), ""), ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    return called


@pytest.mark.parametrize("argv", [[], ["unknown"], ["install", "--now"]])
def test_a_line_it_does_not_take_is_a_usage_error(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as ended:
        server.server(argv)
    assert ended.value.code == 2


def test_linux_install_writes_a_user_unit_and_enables_it_at_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "bin" / "hmz")])
    called = _commands(monkeypatch)
    at = tmp_path / ".config/systemd/user" / server.UNIT
    log = tmp_path / ".local/state/humanize/hmz-web.log"

    assert server.server(["install"]) == 0
    unit = at.read_text()
    assert "WantedBy=default.target" in unit
    assert "User=" not in unit
    assert "Restart=always" in unit
    assert f"StandardOutput=append:{log}" in unit
    assert f"StandardError=append:{log}" in unit
    assert " web --no-open" in unit
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    assert called == [
        ["systemctl", "--user", "show-environment"],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", server.UNIT],
    ]
    assert capsys.readouterr().out == f"hmz server: installed {at}\n"


def test_linux_uninstall_stops_then_removes_the_user_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    at = tmp_path / ".config/systemd/user" / server.UNIT
    at.parent.mkdir(parents=True)
    at.write_text("[Service]\n")
    called = _commands(monkeypatch)

    assert server.server(["uninstall"]) == 0
    assert not at.exists()
    assert called == [
        ["systemctl", "--user", "show-environment"],
        ["systemctl", "--user", "disable", "--now", server.UNIT],
        ["systemctl", "--user", "daemon-reload"],
    ]
    assert capsys.readouterr().out == f"hmz server: uninstalled {at}\n"


def test_mac_install_writes_a_launch_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "bin" / "hmz")])
    called = _commands(monkeypatch)
    at = tmp_path / "Library/LaunchAgents" / f"{server.LABEL}.plist"
    log = tmp_path / "Library/Logs/hmz-web.log"
    domain = f"gui/{os.getuid()}"

    assert server.server(["install"]) == 0
    saved = plistlib.loads(at.read_bytes())
    assert saved["Label"] == server.LABEL
    assert saved["RunAtLoad"] is True
    assert saved["KeepAlive"] is True
    assert saved["ProgramArguments"] == [
        str(tmp_path / "bin" / "hmz"),
        "web",
        "--no-open",
    ]
    assert saved["StandardOutPath"] == str(log)
    assert saved["StandardErrorPath"] == str(log)
    assert called == [["launchctl", "bootstrap", domain, str(at)]]
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    assert capsys.readouterr().out == f"hmz server: installed {at}\n"


def test_mac_uninstall_boots_out_and_removes_the_launch_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    at = tmp_path / "Library/LaunchAgents" / f"{server.LABEL}.plist"
    at.parent.mkdir(parents=True)
    at.write_text("<plist/>")
    called = _commands(monkeypatch)

    assert server.server(["uninstall"]) == 0
    assert not at.exists()
    assert called == [["launchctl", "bootout", f"gui/{os.getuid()}/{server.LABEL}"]]
    assert capsys.readouterr().out == f"hmz server: uninstalled {at}\n"


def test_status_reports_user_systemd_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    at = tmp_path / ".config/systemd/user" / server.UNIT
    at.parent.mkdir(parents=True)
    at.touch()
    called = _commands(
        monkeypatch,
        {
            ("systemctl", "--user", "is-active", server.UNIT): "active\n",
            ("systemctl", "--user", "is-enabled", server.UNIT): "enabled\n",
        },
    )

    assert server.server(["status"]) == 0
    assert called == [
        ["systemctl", "--user", "show-environment"],
        ["systemctl", "--user", "is-active", server.UNIT],
        ["systemctl", "--user", "is-enabled", server.UNIT],
    ]
    assert capsys.readouterr().out == (
        f"hmz server: installed, active, enabled ({at}); "
        f"log: {tmp_path / '.local/state/humanize/hmz-web.log'}\n"
    )


def test_status_reports_an_uninstalled_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert server.server(["status"]) == 0
    assert capsys.readouterr().out == (
        f"hmz server: not installed ({tmp_path / '.config/systemd/user' / server.UNIT})\n"
    )


def test_status_refuses_an_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert server.server(["status"]) == 1
    assert capsys.readouterr().err == (
        "hmz: hmz server status runs on macOS and Linux alone\n"
    )
