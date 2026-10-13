"""A stand-in for `ssh`, and the machine it reaches: this one, under a home of its own.

The `ssh` put first on `PATH` takes what the real one is told -- its options, the destination,
the command -- drops the options and the destination, and runs the command here, with `sh`, in
the other machine's home: its own `HOME`, `HUMANIZE_HOME` and `TMPDIR`. A port it is told to
forward with `-L` it forwards over TCP, for as long as it runs. A destination with `unreachable`
in it is one it cannot reach, as `ssh` says so. Every time it is run it writes its pid and what
it was told to `ssh.log` beside that home.

The machine has an `hmz` in `~/.local/bin` which is this one, saying whichever version it is
said to be installed at, or none, and a `uv` whose `tool install` installs the version asked.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    import pytest

_SSH = """#!{python}
import json, os, socket, subprocess, sys, threading

HOME, HUMANIZE, TMP, LOG = {home!r}, {humanize!r}, {tmp!r}, {log!r}
TAKES = set("BbcDEeFIiJLlmOopQRSWw")

args, forwards, at = sys.argv[1:], [], 0
while at < len(args) and args[at].startswith("-"):
    flag = args[at][1:2]
    if flag in TAKES:
        value = args[at][2:] or args[at + 1]
        at += 1 if args[at][2:] else 2
        if flag == "L":
            forwards.append(value)
    else:
        at += 1
host, command = args[at], " ".join(args[at + 1:])
with open(LOG, "a") as log:
    log.write(json.dumps([os.getpid(), *sys.argv[1:]]) + "\\n")
if "unreachable" in host:
    print(f"ssh: Could not resolve hostname {{host}}: Name or service not known",
          file=sys.stderr)
    sys.exit(255)


def pumps(source, sink):
    try:
        while chunk := source.recv(65536):
            sink.sendall(chunk)
    except OSError:
        pass
    for one in (source, sink):
        try:
            one.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def serves(listening, to):
    while True:
        near, _ = listening.accept()
        try:
            far = socket.create_connection(to)
        except OSError:
            near.close()
            continue
        for there in ((near, far), (far, near)):
            threading.Thread(target=pumps, args=there, daemon=True).start()


for spec in forwards:
    *bind, port, to, to_port = spec.split(":")
    listening = socket.socket()
    listening.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listening.bind((bind[0] if bind else "127.0.0.1", int(port)))
    except OSError as why:
        print(f"bind: {{why}}", file=sys.stderr)
        sys.exit(255)
    listening.listen()
    threading.Thread(
        target=serves, args=(listening, (to, int(to_port))), daemon=True
    ).start()

env = dict(os.environ, HOME=HOME, HUMANIZE_HOME=HUMANIZE, TMPDIR=TMP)
os.chdir(HOME)
if not command:
    threading.Event().wait()
if not forwards:
    os.execvpe("sh", ["sh", "-c", command], env)
sys.exit(subprocess.run(["sh", "-c", command], env=env).returncode)
"""

_HMZ = """#!/bin/sh
if [ ! -f "$HOME/.hmz-version" ]; then echo "sh: hmz: not found" >&2; exit 127; fi
if [ "$1" = "--version" ]; then echo "hmz $(cat "$HOME/.hmz-version")"; exit 0; fi
# What its interface says on stderr is also kept, a stack dumped on SIGABRT among it.
if [ "$1" = "web" ]; then exec {python} -X faulthandler -m hmz "$@" 2>>"$HOME/web.err"; fi
exec {python} -m hmz "$@"
"""

_UV = """#!/bin/sh
echo "$@" >> "$HOME/uv.log"
for said; do case "$said" in hmz==*) version="${said#hmz==}";; esac; done
echo "Resolved 1 package in 3ms"
printf '%s' "$version" > "$HOME/.hmz-version"
echo "Installed 1 executable: hmz"
"""


@dataclass(frozen=True)
class Host:
    """The machine the stand-in reaches.

    Attributes:
      home: Its `HOME`.
      humanize: Its `HUMANIZE_HOME`.
      tmp: Its `TMPDIR`.
      log: Where each `ssh` run writes its pid and what it was told.
    """

    home: Path
    humanize: Path
    tmp: Path
    log: Path

    def installs(self, version: str | None) -> None:
        """Has its `hmz` say this version, or be missing."""
        held = self.home / ".hmz-version"
        if version is None:
            held.unlink(missing_ok=True)
        else:
            held.write_text(version)

    def runs_epics(self) -> None:
        """Has its daemon running, which holds its epics: this process, as one alive."""
        mine = self.tmp / f"humanize-{os.getuid()}"
        mine.mkdir(mode=0o700, exist_ok=True)
        (mine / "daemon.json").write_text(f'{{\n  "pid": {os.getpid()}\n}}\n')

    def installed(self) -> str:
        """What `uv` was asked to install, one line a time."""
        held = self.home / "uv.log"
        return held.read_text() if held.exists() else ""

    def pids(self) -> list[int]:
        """Every `ssh` run so far, by pid."""
        if not self.log.exists():
            return []
        return [json.loads(line)[0] for line in self.log.read_text().splitlines()]

    def told(self) -> list[list[str]]:
        """What every `ssh` run so far was told."""
        if not self.log.exists():
            return []
        return [json.loads(line)[1:] for line in self.log.read_text().splitlines()]


def faked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str | None = "0.0.0"
) -> Host:
    """Puts the stand-in `ssh` first on `PATH`, reaching a machine of its own.

    Args:
      tmp_path: The test's own directory.
      monkeypatch: What puts `PATH` back.
      version: What its `hmz` says it is, or None for none at all.

    Returns:
      The machine.
    """
    there = tmp_path / "there"
    host = Host(
        there / "home",
        there / "humanize",
        # Short, as a socket's path under it must be.
        Path(tempfile.mkdtemp(prefix="r", dir=os.environ["TMPDIR"])),
        there / "ssh.log",
    )
    (host.home / ".local" / "bin").mkdir(parents=True)
    host.humanize.mkdir()
    made = tmp_path / "bin"
    made.mkdir()
    for at, script in (
        (
            made / "ssh",
            _SSH.format(
                python=sys.executable,
                home=str(host.home),
                humanize=str(host.humanize),
                tmp=str(host.tmp),
                log=str(host.log),
            ),
        ),
        (host.home / ".local" / "bin" / "hmz", _HMZ.format(python=sys.executable)),
        (host.home / ".local" / "bin" / "uv", _UV),
    ):
        at.write_text(script)
        at.chmod(0o755)
    monkeypatch.setenv("PATH", f"{made}{os.pathsep}{os.environ['PATH']}")
    host.installs(version)
    return host


def written(*daemons: dict[str, object]) -> None:
    """Writes these daemons down in this machine's settings, as `daemons`."""
    from hmz.coganchor import settings

    settings.changes(lambda held: held.__setitem__("daemons", list(daemons)))
    assert yaml.safe_load(settings.where().read_text())["daemons"]
