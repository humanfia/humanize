"""This machine's daemon and each host it holds, started apart from any terminal.

Each is a fresh interpreter running :mod:`hmz.daemon.detached` -- never a fork of whatever
asked for it, whose threads a fork would copy in whatever state they were in -- in a session of
its own, which is what keeps a hangup from reaching it, with nothing to read and the daemon's
log to write to; it forks once more, while it has no thread to copy, so that it can never take
a controlling terminal again. It says down a pipe that it is listening, or why it could not be,
and whoever started it waits for that.

What it runs in is the environment of whatever started it -- a host the daemon's, the daemon its
first client's -- but for a daemon `hmz daemon serve` runs without a terminal, as the service
`hmz daemon install` writes does: a service manager hands it a bare one, which misses the CLIs
and keys a shell profile adds, so it takes its user's login shell's once as it starts
(Section 3.4.6 of daemon.md).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["settles", "spawns"]

#: How long a login shell is given to say its environment: a profile that hangs or asks
#: something must not keep the daemon from starting.
_ANSWERING = 5.0

#: Written either side of the environment, so that what a profile prints is not read as it.
_MARK = "__HMZ_ENV__"

#: What a shell sets about itself, which is no child's: the directory it was in, how deep it
#: is, and the last command it ran.
_OWN = ("PWD", "OLDPWD", "SHLVL", "_")


def spawns(
    said: Sequence[str],
    seconds: float,
    *,
    keep: Sequence[int] = (),
    env: Mapping[str, str] | None = None,
) -> None:
    """Starts a process apart from the terminal, and comes back once it is up.

    Args:
      said: What it is, as :mod:`hmz.daemon.detached` reads it after the descriptor it says it
        is listening on: `daemon`, or `host` and its workspace, slot and link.
      seconds: How long to wait for it to say so.
      keep: The descriptors besides the standard three and that one it is handed; it holds
        none other of this process's open.
      env: What its environment holds beside this process's own.

    Raises:
      OSError: If it could not be started, or said why it could not come up.
    """
    reading, telling = os.pipe()
    try:
        # Before the process: one buffered here and not yet flushed would be written after
        # what it writes to the same log.
        for stream in (sys.stdout, sys.stderr):
            with contextlib.suppress(Exception):
                stream.flush()
        log = os.open(
            where.at() / where.LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-Pm",
                    "hmz.daemon.detached",
                    str(telling),
                    *said,
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                pass_fds=(telling, *keep),
                start_new_session=True,
                # The daemon's directory is in the temporary directory, which the process
                # started has to find where this one did.
                env={**os.environ, "TMPDIR": tempfile.gettempdir(), **(env or {})},
            )
        finally:
            os.close(log)
    except OSError:
        os.close(reading)
        raise
    finally:
        os.close(telling)
    try:
        _waits(reading, seconds)
    finally:
        os.close(reading)
        # Gone already: it forked the one that says it is up and exited, so that one's own
        # parent is whatever adopts it rather than this.
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(seconds)


def _waits(reading: int, seconds: float) -> None:
    """Waits for the detached process to say it is listening, or for the time to run out."""
    import selectors

    selector = selectors.DefaultSelector()
    selector.register(reading, selectors.EVENT_READ)
    try:
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if not selector.select(0.1):
                continue
            said = os.read(reading, 1 << 12)
            if said.startswith(b"listening"):
                return
            # Gone without a word: it never reached the frame that would have said why.
            raise OSError(
                said.decode(errors="replace").strip()
                or f"it ended before it came up; {where.LOG} says why"
            )
    finally:
        selector.close()


def settles() -> None:
    """Takes :func:`_environment` as this process's own, as `hmz daemon serve` starts."""
    taken = _environment()
    os.environ.clear()
    os.environ.update(taken)


def _environment() -> dict[str, str]:
    """The environment a daemon `hmz daemon serve` runs takes (Section 3.4.6 of daemon.md).

    This process's own where it has a terminal. Where it has none, the one its user's login
    shell gives, or this process's own where that shell does not answer in time, with each
    directory hmz and the CLIs it runs are usually installed to put after `PATH` where it
    lacks it.

    Returns:
      The environment, by name.
    """
    own = dict(os.environ)
    if _terminal():
        return own
    taken = _login() or own
    for one in _OWN:
        taken.pop(one, None)
    home = Path(taken.get("HOME") or Path.home())
    path = [one for one in taken.get("PATH", "").split(os.pathsep) if one]
    for one in (
        str(home / ".local" / "bin"),
        taken.get("UV_TOOL_BIN_DIR", ""),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ):
        if one and one not in path:
            path.append(one)
    taken["PATH"] = os.pathsep.join(path)
    return taken


def _terminal() -> bool:
    """Whether this process has a terminal of its own."""
    try:
        held = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
    except OSError:
        return False
    os.close(held)
    return True


def _login() -> dict[str, str] | None:
    """The environment this user's login shell gives, or None where it does not in time."""
    import pwd

    shell = os.environ.get("SHELL")
    if not shell:
        with contextlib.suppress(KeyError):
            shell = pwd.getpwuid(os.getuid()).pw_shell
    shell = shell or "/bin/sh"
    script = f"printf %s {_MARK}; command env -0; printf %s {_MARK}"
    # Into a file rather than a pipe: something the profile started in the background may
    # hold a pipe open long after the shell is gone.
    with tempfile.TemporaryFile() as out:
        try:
            subprocess.run(
                [shell, "-ilc", script],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.DEVNULL,
                timeout=_ANSWERING,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        out.seek(0)
        said = out.read()
    mark = _MARK.encode()
    start = said.find(mark)
    end = said.find(mark, start + len(mark)) if start >= 0 else -1
    if end < 0:
        return None
    taken: dict[str, str] = {}
    for entry in said[start + len(mark) : end].split(b"\0"):
        name, eq, value = entry.partition(b"=")
        if name and eq:
            taken[os.fsdecode(name)] = os.fsdecode(value)
    return taken
