"""``hmz daemon`` -- this machine's daemon: run, reached, paired, installed (cli.md, 13).

- `serve [--listen <spec>]...`: runs the daemon in the foreground, until interrupted.
- `connect --stdio`: carries this process's standard streams to the daemon's socket, which is
  what a `stdio:` route runs on the far machine.
- `pair [--route <route>]... [--seconds <seconds>]`: makes a pairing code.
- `devices [revoke <name>]`: lists the paired devices, or revokes one.
- `install` and `uninstall`: the launchd agent or systemd user unit that keeps it running.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

__all__ = ["daemon"]

#: The launchd agent's label, and so its file's name.
LABEL = "ai.humanfia.hmz.daemon"

#: The systemd user unit's name.
UNIT = "hmz-daemon.service"


def _listener(said: str) -> str:
    import argparse

    from hmz.daemon.listening import spec

    try:
        spec(said)
    except ValueError as why:
        raise argparse.ArgumentTypeError(str(why)) from None
    return said


def _route(said: str) -> str:
    import argparse

    from hmz.reach import Route

    try:
        Route.parse(said)
    except ValueError as why:
        raise argparse.ArgumentTypeError(str(why)) from None
    return said


def _seconds(said: str) -> int:
    import argparse

    if not said.isdigit() or not 60 <= int(said) <= 86_400:  # noqa: PLR2004
        msg = f"{said} is not a number of seconds from 60 to 86400"
        raise argparse.ArgumentTypeError(msg)
    return int(said)


def _parser() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz daemon",
        description="Run, reach, pair and install this machine's daemon.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND", required=True)
    serve = doing.add_parser("serve", help="run the daemon in the foreground")
    serve.add_argument(
        "--listen",
        type=_listener,
        action="append",
        default=[],
        metavar="SPEC",
        help="a listener to open beside the socket; any number of times",
    )
    connect = doing.add_parser(
        "connect", help="carry standard input and output to the daemon's socket"
    )
    connect.add_argument("--stdio", action="store_true", required=True)
    pair = doing.add_parser("pair", help="make a code that pairs one device")
    pair.add_argument(
        "--route",
        type=_route,
        action="append",
        default=[],
        metavar="ROUTE",
        help="a route the code carries; the listeners' where none is given",
    )
    pair.add_argument("--seconds", type=_seconds, default=600, metavar="SECONDS")
    devices = doing.add_parser("devices", help="list the paired devices, or revoke one")
    devices.add_argument("revoke", nargs="?", choices=["revoke"])
    devices.add_argument("name", nargs="?")
    doing.add_parser("install", help="run the daemon as a service at login")
    doing.add_parser("uninstall", help="remove that service")
    return parser


def daemon(argv: list[str]) -> int:
    """Runs one `hmz daemon` command.

    Args:
      argv: What followed `daemon`.

    Returns:
      Its exit status.
    """
    parser = _parser()
    line = parser.parse_args(argv)
    if line.doing == "devices" and (line.revoke is None) != (line.name is None):
        parser.error("devices takes nothing, or revoke and one name")
    if line.doing == "serve":
        return _serve(line.listen)
    if line.doing == "connect":
        return _connect()
    if line.doing in ("install", "uninstall"):
        return _service(install=line.doing == "install")
    if line.doing == "pair":
        params: dict[str, Any] = {"seconds": line.seconds}
        if line.route:
            params["routes"] = line.route
        return _called("pair.create", params, _paired)
    if line.name is None:
        return _called("devices.list", {}, _listed)
    name: str = line.name

    def revoked(said: dict[str, Any]) -> None:
        print(f"hmz daemon devices: revoked {name}; {said['dropped']} sessions closed")

    return _called("devices.revoke", {"name": name}, revoked)


def _serve(listen: list[str]) -> int:
    """`hmz daemon serve`: the daemon in this process, until `SIGINT` or `SIGTERM`."""
    import contextlib
    import errno
    import signal

    from hmz.daemon import routing, where
    from hmz.daemon.detaching import settles

    def stops(_signal: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stops)
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        # Once, before anything is started: every host takes the daemon's environment.
        settles()
        routing.serves(
            listen=listen,
            kept=True,
            opened=lambda route: print(f"hmz daemon: listening on {route}", flush=True),
        )
    except KeyboardInterrupt:
        return 0
    except OSError as why:
        if why.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            pid = where.held(where.at()).get("pid")
            print(f"hmz: a daemon is already running (pid {pid})", file=sys.stderr)
        else:
            print(f"hmz: the daemon cannot be reached: {why}", file=sys.stderr)
        return 1
    return 0


def _unreached(why: OSError) -> int:
    import errno

    if why.errno == errno.EADDRINUSE:
        print(f"hmz: {why.strerror or why}", file=sys.stderr)
    else:
        print(f"hmz: the daemon cannot be reached: {why}", file=sys.stderr)
    return 1


def _connect() -> int:
    """`hmz daemon connect --stdio`: standard streams spliced to the daemon's socket."""
    import contextlib
    import os
    import signal

    def interrupted(_signal: int, _frame: object) -> None:
        # Somebody stopping the line, as the desktop app stops the process of every pipe it
        # closes: it exits as the interrupt would have had it, without a traceback. Ended
        # here rather than raised, which into the wait of the splice may leave a lock of it
        # released twice, and that is a traceback as well.
        os._exit(128 + signal.SIGINT)

    held = False
    with contextlib.suppress(ValueError):  # off the main thread, where none reaches
        # An interrupt somebody chose to have ignored stays so.
        if signal.getsignal(signal.SIGINT) is signal.default_int_handler:
            signal.signal(signal.SIGINT, interrupted)
            held = True
    try:
        from hmz import daemon
        from hmz.reach import SYNC, dial, splice, stdio

        try:
            pipe = dial("unix:", start=daemon.start)
        except OSError as why:
            return _unreached(why)
        here = stdio()
        # What the client discards everything up to: what a shell printed before this ran.
        here.sendall(SYNC)
        splice(here, pipe)
    finally:
        if held:
            signal.signal(signal.SIGINT, signal.default_int_handler)
    return 0


def _called(method: str, params: dict[str, Any], said: Any) -> int:
    """Calls one method of this machine's daemon, started where none runs, and says the answer."""
    from hmz import daemon
    from hmz.daemon import where
    from hmz.daemon.link import dialed
    from hmz.rpc import Closed, RpcError

    try:
        daemon.start()
        peer, _ = dialed(where.at(), kind="cli")
    except OSError as why:
        return _unreached(why)
    try:
        answer = peer.call(method, params, timeout=30)
    except RpcError as why:
        print(f"hmz: {why.message}", file=sys.stderr)
        return 1
    except (Closed, TimeoutError) as why:
        print(f"hmz: the daemon cannot be reached: {why}", file=sys.stderr)
        return 1
    finally:
        peer.close()
    said(answer)
    return 0


def _paired(said: dict[str, Any]) -> None:
    import datetime

    print(said["code"], flush=True)
    until = datetime.datetime.fromtimestamp(int(said["expires"])).astimezone()
    print(
        "hmz daemon pair: claim this code on the device to pair before "
        f"{until:%Y-%m-%d %H:%M:%S %Z}",
        file=sys.stderr,
    )


def _listed(said: dict[str, Any]) -> None:
    for one in said["devices"]:
        print(
            "\t".join(
                [one["name"], one["fingerprint"], one["added"], one["seen"] or ""]
            )
        )


def _service(*, install: bool) -> int:
    """`hmz daemon install` and `uninstall`: the service of Section 3.9.6 of daemon.md.

    A unit an earlier hmz wrote under `~/.config` while `XDG_CONFIG_HOME` names elsewhere goes
    once the service is installed or uninstalled, never before, so that two are never left and a
    failed install leaves the one there was; uninstalled, it is the service where it is the only
    one.
    """
    import os
    import subprocess
    from pathlib import Path

    stale: list[Path] = []
    if sys.platform == "darwin":
        at = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        domain = f"gui/{os.getuid()}"
        steps = (
            [["launchctl", "bootstrap", domain, str(at)]]
            if install
            else [["launchctl", "bootout", f"{domain}/{LABEL}"]]
        )
        text = _plist(_hmz())
    elif sys.platform.startswith("linux"):
        at = _configured() / "systemd" / "user" / UNIT
        # Where every hmz before this one wrote it, whatever XDG_CONFIG_HOME named.
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
        text = _unit(_hmz())
    else:
        print("hmz: hmz daemon install runs on macOS and Linux alone", file=sys.stderr)
        return 1
    if not install and not at.exists():
        if not stale:
            print(f"hmz: no service is installed at {at}", file=sys.stderr)
            return 1
        at = stale.pop()
    if install:
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_text(text, encoding="utf-8")
    for step in steps:
        try:
            ran = subprocess.run(step, capture_output=True, text=True, check=False)
        except OSError as why:
            print(f"hmz: {why}", file=sys.stderr)
            return 1
        if ran.returncode:
            print(f"hmz: {(ran.stderr or ran.stdout).strip()}", file=sys.stderr)
            return 1
    for unit in stale:
        (unit.parent / "default.target.wants" / UNIT).unlink(missing_ok=True)
        unit.unlink()
    if not install:
        at.unlink()
    if (stale or not install) and sys.platform.startswith("linux"):
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"], check=False, capture_output=True
        )
    print(f"hmz daemon: {'installed' if install else 'uninstalled'} {at}")
    return 0


def _configured() -> Path:
    """Where the user's systemd manager looks for its configuration.

    Its own `XDG_CONFIG_HOME`, not this shell's, which a shell's startup files may set and the
    manager never see; `~/.config` where the manager cannot be asked, names none, or names a
    relative one, which the XDG Base Directory Specification says to ignore.
    """
    import subprocess
    from pathlib import Path

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


def _hmz() -> Path:
    """The absolute path of the hmz that runs this."""
    import shutil
    from pathlib import Path

    # Not resolved: a link an installer keeps in place across upgrades is what stays there.
    ran = sys.argv[0]
    found = shutil.which("hmz") if ran.endswith(".py") else shutil.which(ran)
    return Path(found or ran).absolute()


def _plist(hmz: Path) -> str:
    """The launchd agent that runs `<hmz> daemon serve` at login and keeps it running."""
    from xml.sax.saxutils import escape

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{escape(str(hmz))}</string>
    <string>daemon</string>
    <string>serve</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
"""


def _unit(hmz: Path) -> str:
    """The systemd user unit that runs `<hmz> daemon serve` at login and keeps it running."""
    return f"""[Unit]
Description=hmz daemon

[Service]
ExecStart="{hmz}" daemon serve
Restart=always

[Install]
WantedBy=default.target
"""
