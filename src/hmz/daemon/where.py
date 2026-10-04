"""Where this machine's daemon keeps its socket, and what is written down beside it.

One daemon per machine and user, holding the runs of every workspace there: one directory,
with the socket frontends reach it through and a note of what is running there. The note is
what tells a daemon that is running from one whose machine went down without it -- a socket
file outlives the process that bound it, and a stale one is a frontend that hangs.

In the machine's temporary directory rather than under humanize's home, because a daemon is a
process and a process is one machine's: a home directory many machines mount would have each
of them read the others' notes, and check another kernel's pid against its own.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import socket
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import machine

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "LOCK",
    "LOG",
    "RECORD",
    "SOCKET",
    "alive",
    "at",
    "connects",
    "held",
    "holds",
    "now",
    "reached",
    "workspace",
    "wrote",
]

#: The socket a frontend reaches the runs through, inside the daemon's directory.
SOCKET = "daemon.sock"

#: What is written down about the daemon there: which process, since when, of which protocol.
RECORD = "daemon.json"

#: Where whatever belongs to no run goes: what the daemon could not say to a frontend -- a
#: crash before any run was started, a round of messages it could not carry -- and a
#: directory that went away under whoever was reaching for the socket. What belongs to a run
#: is written into that run's epic instead.
LOG = "daemon.log"

#: What the one daemon of this machine holds for as long as it is running. A lock rather than
#: a file that is looked at: the kernel drops it when the process goes, however it goes, so
#: there is no such thing as one left behind by a machine that was turned off.
LOCK = "daemon.lock"

#: The longest a socket may be reached by its whole path. What a Unix socket address holds is
#: about a hundred bytes -- 108 on Linux, 104 on macOS -- and the shorter of the two is what
#: is measured against, so that a humanize which works here works there. A path longer than
#: this is reached by standing in its directory and naming the socket alone.
_LONGEST = 100


def at() -> Path:
    """The directory this machine's daemon keeps its socket in, made private where it is not yet.

    This user's own directory in the machine's temporary directory, which nothing but humanize
    names: one fixed place per machine and user, so that every frontend on the machine finds
    the one daemon, and short, so that its socket is an address whole.

    Raises:
      PermissionError: If it is one somebody else could write, and so could have planted a
        socket in.
    """
    return machine()


def workspace(where: str | os.PathLike[str] | None = None) -> str:
    """A workspace as the daemon knows it by: the whole path, with every link followed.

    Args:
      where: The project directory, or None for wherever humanize is being run.

    Returns:
      The path, which two spellings of one directory are one of.
    """
    return str(Path(where or Path.cwd()).resolve())


@contextlib.contextmanager
def reached(where: Path) -> Generator[str]:
    """The socket in one daemon's directory, spelled short enough to be a socket address.

    A Unix socket is reached by a path of about a hundred bytes, whole, and a project under a
    deep home directory is longer than that. Standing in the directory and naming the socket
    alone is what makes the name short enough, and is what every program that meets this does.

    Args:
      where: The daemon's own directory.

    Yields:
      The socket, as it is to be bound or connected -- the whole path where that fits, and
      the name alone where it does not.

    Note:
      Where it does not fit, this changes the directory of the whole process for as long as
      the socket is being reached. It is done where a process has one thread -- opening the
      interface, and answering a line about a run -- and never while a flow is running, which
      is a flow that may be standing somewhere of its own.

      Where the directory it set out from has gone by the time it is over, that is written
      down beside the socket rather than raised. This is a `finally`: raising here would put
      a directory that went away in place of whatever the socket itself had to say, and every
      caller reads an `OSError` from this as the socket being unreachable -- which would turn
      a daemon that bound perfectly well into one that never came up. What must not happen is
      the quiet version, a run left standing somewhere it was never asked to run and no line
      anywhere saying so.
    """
    whole = where / SOCKET
    if len(str(whole).encode()) <= _LONGEST:
        yield str(whole)
        return
    was = Path.cwd()
    try:
        # The move is under the same `try` as what undoes it, so that a signal arriving in
        # the breath between the two cannot be the thing that leaves the process here. The
        # cost is putting a process back where it already is when the move itself failed,
        # which is one syscall and never wrong.
        os.chdir(where)
        yield SOCKET
    finally:
        try:
            os.chdir(was)
        except OSError:
            _logged(where, f"a run reaching for its socket could not go back to {was}")


def connects(where: Path, seconds: float | None = None) -> socket.socket:
    """Connects to the socket in one daemon's directory.

    Args:
      where: The daemon's own directory.
      seconds: How long connecting is given, or None for as long as it takes -- which the
        socket keeps, for whatever is asked of it next.

    Returns:
      The socket, connected.

    Raises:
      OSError: If nothing is listening there.
    """
    one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        one.settimeout(seconds)
        with reached(where) as reaching:
            one.connect(reaching)
    except OSError:
        one.close()
        raise
    return one


def _logged(where: Path, about: str) -> None:
    """Writes down beside the socket what there was no terminal to say.

    The daemon's own log, written here rather than through :func:`hmz.daemon.carrying.logged`:
    every other module of this package reaches for this one, so this one reaches for none of
    them.

    Args:
      where: The daemon's own directory.
      about: What was being done, since whatever is being handled is what raised.
    """
    with (
        contextlib.suppress(OSError),
        (where / LOG).open("a", encoding="utf-8") as writing,
    ):
        writing.write(f"{about}\n{traceback.format_exc()}\n")


def holds(where: Path) -> int:
    """Takes the one daemon of this machine, for as long as this process lives.

    One daemon per machine: two would be two answers to which workspace is held where, and two
    hosts of one project are two flows writing over each other's epic. A lock rather than a
    file somebody looks at, because looking is what leaves a window between the look and the
    socket -- two `hmz` started in the same second would both find nothing and both bind.

    Args:
      where: The daemon's own directory, which must already be there.

    Returns:
      The descriptor holding it, which is to be kept open for as long as the daemon runs and
      is dropped by the kernel however the process ends.

    Raises:
      OSError: If another process is already holding it, or the file cannot be made.
    """
    import fcntl

    taking = os.open(str(where / LOCK), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(taking, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(taking)
        raise
    return taking


def wrote(where: Path, said: dict[str, Any]) -> None:
    """Writes down what is running here, whole and then moved into place.

    Beside it under a name nothing else will pick rather than a fixed `.new`, as every file
    humanize writes is, and on disk before it is moved: a frontend reading it finds the old
    note or the new one. `0600`, as everything else in the daemon's directory is.

    Args:
      where: The daemon's own directory.
      said: What to write.
    """
    import tempfile

    handle, beside = tempfile.mkstemp(dir=where, prefix=f".{RECORD}.", suffix=".new")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(json.dumps(said, indent=2) + "\n")
            writing.flush()
            os.fsync(handle)
        Path(beside).replace(where / RECORD)
    except BaseException:
        Path(beside).unlink(missing_ok=True)
        raise


def now() -> str:
    """This moment, to the second, which is how long a note of when a process started has to be.

    Returns:
      It, in UTC, as `%Y-%m-%dT%H:%M:%SZ`.
    """
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def held(where: Path) -> dict[str, Any]:
    """What is written down about the daemon there, and nothing at all where nothing is.

    Args:
      where: The daemon's own directory.

    Returns:
      What it says about itself, or an empty mapping for a directory holding no daemon, one
      whose note cannot be read, and one whose process is no longer there.
    """
    try:
        said: object = json.loads((where / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(said, dict):
        return {}
    held = cast("dict[str, Any]", said)
    pid = held.get("pid")
    if not isinstance(pid, int) or not alive(pid):
        return {}
    return held


def alive(pid: int) -> bool:
    """Whether a process of that number is still there.

    Args:
      pid: The process.

    Returns:
      Whether it exists. A process somebody else owns still counts as running: this asks
      whether the daemon is there, not whether it could be signalled.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as why:
        return why.errno == errno.EPERM
    return True
