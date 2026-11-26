"""``hmz server`` -- install and manage the web interface as a login service."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

__all__ = ["server"]

LABEL = "ai.humanfia.hmz.web"
UNIT = "hmz-web.service"


def _parser() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz server",
        description="Install and manage the web interface as a service at login.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND", required=True)
    doing.add_parser("install", help="install and start at login")
    doing.add_parser("uninstall", help="stop and remove the per-user service")
    doing.add_parser("status", help="show whether the service is installed and running")
    return parser


def server(argv: list[str]) -> int:
    """Runs one `hmz server` command."""
    line = _parser().parse_args(argv)
    if line.doing == "status":
        return _status()
    return _service(install=line.doing == "install")


def _hmz() -> Path:
    import shutil

    ran = sys.argv[0]
    found = shutil.which("hmz") if ran.endswith(".py") else shutil.which(ran)
    return Path(found or ran).absolute()


def _configured() -> Path:
    try:
        ran = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        ran = None
    if ran is not None and not ran.returncode:
        for line in ran.stdout.splitlines():
            name, _, value = line.partition("=")
            if name == "XDG_CONFIG_HOME" and Path(value).is_absolute():
                return Path(value)
    return Path.home() / ".config"


def _log() -> Path:
    """The log file the service writes to."""
    if sys.platform == "darwin":
        log = Path.home() / "Library" / "Logs" / "hmz-web.log"
    elif sys.platform.startswith("linux"):
        log = Path.home() / ".local" / "state" / "humanize" / "hmz-web.log"
    else:
        raise OSError("hmz server runs on macOS and Linux alone")
    return log


def _unit(hmz: Path, log: Path) -> str:
    """The systemd user unit that runs `<hmz> web --no-open` at login and keeps it running."""
    return f"""[Unit]
Description=hmz web interface

[Service]
ExecStart="{hmz}" web --no-open
Restart=always
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


def _plist(hmz: Path, log: Path) -> str:
    """The launchd agent that runs `<hmz> web --no-open` at login and keeps it running."""
    from xml.sax.saxutils import escape

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{escape(LABEL)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{escape(str(hmz))}</string>
    <string>web</string>
    <string>--no-open</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{escape(str(log))}</string>
  <key>StandardErrorPath</key>
  <string>{escape(str(log))}</string>
</dict>
</plist>
"""


def _prepare_log(log: Path) -> None:
    """Make sure the log file exists and is only readable by the user."""
    log.parent.mkdir(parents=True, exist_ok=True)
    log.touch(mode=0o600, exist_ok=True)
    log.chmod(0o600)


def _run(step: list[str]) -> bool:
    try:
        ran = subprocess.run(step, capture_output=True, text=True, check=False)
    except OSError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return False
    if ran.returncode:
        print(
            f"hmz: {(ran.stderr or ran.stdout).strip() or f'{step[0]} failed'}",
            file=sys.stderr,
        )
        return False
    return True


def _service(*, install: bool) -> int:
    stale: list[Path] = []
    if sys.platform == "darwin":
        at = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        domain = f"gui/{os.getuid()}"
        steps = (
            [["launchctl", "bootstrap", domain, str(at)]]
            if install
            else [["launchctl", "bootout", f"{domain}/{LABEL}"]]
        )
    elif sys.platform.startswith("linux"):
        at = _configured() / "systemd" / "user" / UNIT
        released = Path.home() / ".config" / "systemd" / "user" / UNIT
        stale = (
            [released]
            if released.exists() and released.resolve() != at.resolve()
            else []
        )
        steps = (
            [
                ["systemctl", "--user", "daemon-reload"],
                ["systemctl", "--user", "enable", "--now", UNIT],
            ]
            if install
            else [["systemctl", "--user", "disable", "--now", UNIT]]
        )
    else:
        print("hmz: hmz server install runs on macOS and Linux alone", file=sys.stderr)
        return 1
    if not install and not at.exists():
        if not stale:
            print(f"hmz: no service is installed at {at}", file=sys.stderr)
            return 1
        at = stale.pop()

    try:
        if install:
            log = _log()
            _prepare_log(log)
            at.parent.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                text = _plist(_hmz(), log)
            elif sys.platform.startswith("linux"):
                text = _unit(_hmz(), log)
            else:
                print(
                    "hmz: hmz server install runs on macOS and Linux alone",
                    file=sys.stderr,
                )
                return 1
            at.write_text(text, encoding="utf-8")
    except OSError as why:
        print(f"hmz: cannot prepare the web service: {why}", file=sys.stderr)
        return 1

    for step in steps:
        if not _run(step):
            return 1
    for old in stale:
        (old.parent / "default.target.wants" / UNIT).unlink(missing_ok=True)
        old.unlink()
    if not install:
        try:
            at.unlink()
        except OSError as why:
            print(f"hmz: cannot remove {at}: {why}", file=sys.stderr)
            return 1
    if (stale or not install) and sys.platform.startswith("linux"):
        _run(["systemctl", "--user", "daemon-reload"])
    print(f"hmz server: {'installed' if install else 'uninstalled'} {at}")
    return 0


def _status() -> int:
    if sys.platform == "darwin":
        at = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        domain = f"gui/{os.getuid()}"
    elif sys.platform.startswith("linux"):
        at = _configured() / "systemd" / "user" / UNIT
    else:
        print("hmz: hmz server status runs on macOS and Linux alone", file=sys.stderr)
        return 1
    if not at.exists():
        print(f"hmz server: not installed ({at})")
        return 0
    try:
        if sys.platform == "darwin":
            loaded = subprocess.run(
                ["launchctl", "print", f"{domain}/{LABEL}"],
                capture_output=True,
                text=True,
                check=False,
            )
            state = "loaded" if loaded.returncode == 0 else "not loaded"
        elif sys.platform.startswith("linux"):
            active = subprocess.run(
                ["systemctl", "--user", "is-active", UNIT],
                capture_output=True,
                text=True,
                check=False,
            )
            enabled = subprocess.run(
                ["systemctl", "--user", "is-enabled", UNIT],
                capture_output=True,
                text=True,
                check=False,
            )
            if (
                active.returncode not in (0, 3)
                or enabled.returncode not in (0, 1)
                or not active.stdout.strip()
                or not enabled.stdout.strip()
            ):
                message = (
                    active.stderr or enabled.stderr
                ).strip() or "systemctl did not report the service state"
                print(
                    f"hmz: {message}",
                    file=sys.stderr,
                )
                return 1
            state = f"{active.stdout.strip()}, {enabled.stdout.strip()}"
        else:
            print(
                "hmz: hmz server status runs on macOS and Linux alone", file=sys.stderr
            )
            return 1
    except OSError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"hmz server: installed, {state} ({at}); log: {_log()}")
    return 0
