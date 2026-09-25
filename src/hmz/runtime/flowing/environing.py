"""The environment driver both backends share, and the machine it is written against.

An environment is a working directory on a machine, and everything a flow asks of one comes
down to a handful of things done on that machine: start a program, read or write a file,
make or remove a directory, copy a tree, add a git worktree. So the driver is written once,
here -- :class:`MachineEnvDriver`, against a :class:`Machine` -- and each backend is a
machine: :mod:`.environing_local` for this one and :mod:`.environing_ssh` for one reached over
ssh. Everything a driver derives -- a subdirectory, a worktree, a temporary copy, a scratch
directory -- is another driver on the same machine object, so they share its connection.

Where what a driver makes lives, on the machine it makes it on, under humanize's own home
there (`hmz.home()` here, `${HUMANIZE_HOME:-~/.humanize}` over ssh)::

    envs/<name>-<digest>/            one per workdir things are derived from
        clones/<id>-<digest>/        a temporary copy, kept until destroyed
        clones/<id>-<digest>.lock    held by whichever process holds the copy (this machine)
        scratch/<id>-<digest>/       a scratch directory, kept until destroyed
        worktrees/<ref>-<random>/    a worktree added with no `dir` of its own

Under humanize's home rather than the system's temporary directory for three reasons. A
resumable run keeps its copies across a reboot, which a temporary directory that is a tmpfs
or is swept by `systemd-tmpfiles` does not promise. A copy is a reflink only on the
filesystem the workdir is on, and a home directory is far likelier to share one with a
project than `/tmp` is. And one directory holds all of it: `envs/` can be removed whenever no
run is using it.

Every name is deterministic -- the digest is of the workdir's absolute path, and of the id --
so a resumed run that derives the same id from the same workdir finds the copy it left. A
copy is made beside its final place and renamed into it, so one that is there is whole.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import hashlib
import logging
import posixpath
import re
import secrets
import shlex
import threading
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Protocol

from hmz.flows import (
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    EnvUnavailable,
    ScratchError,
    TempCloneBusy,
    WorktreeError,
)

from .spi import ENV_CAPABILITIES

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from hmz.flows import EnvBackendKind

    from .spi import Placement

__all__ = [
    "CLONE_SCRIPT",
    "ENVS",
    "GPU_QUERY",
    "KILLED_WITHIN",
    "REMOVE_SCRIPT",
    "Claim",
    "Machine",
    "MachineEnvDriver",
    "Resources",
    "Running",
    "clone_dir",
    "env_error",
    "exit_status",
    "gpus_of",
    "home_of",
    "scratch_dir",
    "started_error",
    "tidy_workdir",
    "worktree_dir",
]

log = logging.getLogger(__name__)

#: The directory under humanize's home on a machine that everything derived there lives in.
ENVS = "envs"

#: Errnos that mean the machine, rather than the path, is the trouble.
_CONNECTION = frozenset(
    {
        errno.EPIPE,
        errno.ECONNRESET,
        errno.ECONNREFUSED,
        errno.ECONNABORTED,
        errno.ETIMEDOUT,
        errno.EHOSTUNREACH,
        errno.ENETUNREACH,
        errno.ESHUTDOWN,
        errno.ENOTCONN,
    }
)

#: Errnos that mean permission was refused.
_REFUSED = frozenset({errno.EACCES, errno.EPERM, errno.EROFS})

#: How long a command that was killed is given to be gone before it is let go of anyway.
KILLED_WITHIN = 10.0

#: How long a command may be in a message before it is cut short.
_SHOWN = 120

#: How many fields each line :data:`GPU_QUERY` prints has.
_GPU_FIELDS = 3

#: Copying a tree, in POSIX sh, so that it is the same copy on every machine: `$1` to `$2`.
#:
#: A copy that is already there is taken as it is -- which is how a resumed run finds the one
#: it left -- and one is only ever there whole, since it is made under a name of its own
#: beside its place, `<place>.part.<pid>`, and renamed into it only where nothing is there
#: yet. What a copy or a removal left there is swept once the process making it is gone, and
#: not before: two processes copying one id at once end with one whole copy between them.
#: The copy is a reflink where the filesystem can make one: GNU `cp --reflink=auto`, then
#: macOS's `cp -c`, then a plain copy.
#:
#: A repository copied along with its workdir is made to stand alone, since a copy that names
#: the original's files by absolute path shares its `HEAD` and index with it -- a commit in
#: the copy moving the original's branch.
#:
#: - A `.git` directory is a repository of its own once copied. The linked worktrees it names
#:   that were copied with it -- ones kept inside the workdir, by the name it was given or
#:   the one it really has -- are pointed at the copy, and it at them, where the copy is about
#:   to be; ones named relative to each other inside it stay so. The ones outside it are the
#:   original's and are dropped.
#: - A `.git` file is a linked worktree whose repository is elsewhere. It is replaced with a
#:   repository cloned from that one, sharing its objects rather than copying them, checked
#:   out where the original is, with the original's index. Paths are made absolute by `cd`
#:   and `pwd -P` rather than `git rev-parse --path-format`, which git before 2.31 lacks.
#: - Any `.git` file left below that still names a repository outside the copy -- by an
#:   absolute path, or a relative one that leads out of it -- is removed, leaving that
#:   directory part of the copy's own repository. A submodule's names its repository relative
#:   to itself, inside the copy, and is kept.
CLONE_SCRIPT = r"""
set -eu
src=$1 dst=$2
[ -d "$src" ] || { echo "there is no directory $src to copy" >&2; exit 2; }
[ ! -e "$dst" ] || exit 0
real=$(cd -- "$src" && pwd -P)
for stale in "$dst".part.*; do
  [ -e "$stale" ] || continue
  owner=${stale##*.}
  case $owner in ''|*[!0-9]*) continue ;; esac
  kill -0 "$owner" 2>/dev/null || rm -rf -- "$stale" 2>/dev/null || :
done
part=$dst.part.$$
mkdir -p -- "$part"
here=$(cd -- "$part" && pwd -P)
if ! cp -a --reflink=auto -- "$src/." "$part/" 2>/dev/null; then
  rm -rf -- "$part"; mkdir -p -- "$part"
  if ! cp -ac -- "$src/." "$part/" 2>/dev/null; then
    rm -rf -- "$part"; mkdir -p -- "$part"
    cp -a -- "$src/." "$part/"
  fi
fi
if [ -d "$part/.git" ]; then
  rm -f -- "$part/.git/index.lock"
  for admin in "$part"/.git/worktrees/*; do
    [ -d "$admin" ] || continue
    was=$(cat -- "$admin/gitdir" 2>/dev/null) || was=
    rel=
    case $was in
      "$src"/*/.git) rel=${was#"$src"/} ;;
      "$real"/*/.git) rel=${was#"$real"/} ;;
      /*) ;;
      ?*)
        there=$(cd -- "$admin" 2>/dev/null && cd -- "$(dirname -- "$was")" 2>/dev/null \
          && pwd -P) || there=
        case $there in "$here"/*) continue ;; esac ;;
    esac
    rel=${rel%/.git}
    if [ -n "$rel" ] && [ -f "$part/$rel/.git" ]; then
      printf '%s\n' "$dst/$rel/.git" > "$admin/gitdir"
      printf 'gitdir: %s\n' "$dst/.git/worktrees/${admin##*/}" > "$part/$rel/.git"
      continue
    fi
    rm -rf -- "$admin"
  done
elif [ -f "$part/.git" ]; then
  common=$(cd -- "$src" && cd -- "$(git rev-parse --git-common-dir)" && pwd -P)
  gitdir=$(cd -- "$src" && cd -- "$(git rev-parse --git-dir)" && pwd -P)
  head=$(git -C "$src" symbolic-ref -q HEAD) || head=
  sha=$(git -C "$src" rev-parse -q --verify HEAD) || sha=
  rm -f -- "$part/.git"
  git clone -q --bare --shared -- "$common" "$part/.git"
  git --git-dir="$part/.git" config core.bare false
  if [ -n "$head" ]; then
    git --git-dir="$part/.git" symbolic-ref HEAD "$head"
    [ -z "$sha" ] || git --git-dir="$part/.git" update-ref "$head" "$sha"
  elif [ -n "$sha" ]; then
    git --git-dir="$part/.git" update-ref --no-deref HEAD "$sha"
  fi
  [ ! -f "$gitdir/index" ] || cp -- "$gitdir/index" "$part/.git/index"
fi
find "$part" -mindepth 2 -name .git -type f 2>/dev/null | while IFS= read -r file; do
  at=$(sed -n 's/^gitdir: //p' "$file")
  case $at in
    '' | "$dst"/*) continue ;;
    /*) ;;
    *)
      there=$(cd -- "$(dirname -- "$file")" 2>/dev/null && cd -- "$at" 2>/dev/null \
        && pwd -P) || there=
      case $there in "$here"/*) continue ;; esac ;;
  esac
  rm -f -- "$file"
done
if mv -T -- "$part" "$dst" 2>/dev/null; then :
elif [ -e "$dst" ]; then rm -rf -- "$part"
else mv -- "$part" "$dst"
fi
"""

#: Removing a tree, `$1`. Renamed out of its place first, so that the name is either the
#: whole tree or nothing however the removal ends -- a copy half removed and then found again
#: would be taken for a whole one -- and under a name the next copy made beside it sweeps.
#: Made writable where `rm -rf` alone cannot empty it, as a read-only module cache is not.
REMOVE_SCRIPT = r"""
if [ -L "$1" ]; then rm -f -- "$1"; exit; fi
[ -e "$1" ] || exit 0
gone=$1.part.gone.$$
mv -- "$1" "$gone" || exit 1
rm -rf -- "$gone" 2>/dev/null && exit 0
chmod -R u+rwX -- "$gone" 2>/dev/null
rm -rf -- "$gone"
"""

# ------------------------------------------------------------------------------ resources


@dataclass(frozen=True, slots=True)
class Resources:
    """What a machine has, as far as a flow's resource mixins ask.

    Attributes:
      cpu_count: Logical CPUs this user's processes may run on.
      memory: Memory, in bytes.
      gpu_count: GPUs a process started there sees.
      gpu_memory: Memory of the smallest of them, in bytes; 0 with none.
    """

    cpu_count: int = 1
    memory: int = 0
    gpu_count: int = 0
    gpu_memory: int = 0


#: What asks `nvidia-smi` for the GPUs, one line apiece: index, uuid, memory in MiB.
GPU_QUERY = (
    "nvidia-smi",
    "--query-gpu=index,uuid,memory.total",
    "--format=csv,noheader,nounits",
)


def gpus_of(said: Iterable[str], visible: str | None) -> tuple[int, int]:
    """The GPUs a process sees, from what :data:`GPU_QUERY` printed.

    Args:
      said: Its lines.
      visible: `CUDA_VISIBLE_DEVICES` where it is set, which narrows them the way CUDA does:
        indices and `GPU-` uuid prefixes, comma-separated, read up to the first one that is
        neither; empty for none. None for every GPU there is.

    Returns:
      How many, and the memory of the smallest in bytes (0 with none).
    """
    gpus: list[tuple[int, str, int]] = []
    for line in said:
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < _GPU_FIELDS or not fields[0].isdigit():
            continue
        mib = int(fields[2]) if fields[2].isdigit() else 0
        gpus.append((int(fields[0]), fields[1], mib * 1024 * 1024))
    if visible is not None:
        chosen: list[tuple[int, str, int]] = []
        for token in (one.strip() for one in visible.split(",")):
            if token.isdigit():
                found = [gpu for gpu in gpus if gpu[0] == int(token)]
            elif token.startswith("GPU-"):
                found = [gpu for gpu in gpus if gpu[1].startswith(token)]
            else:
                break
            if not found:
                break
            if found[0] not in chosen:
                chosen.append(found[0])
        gpus = chosen
    return len(gpus), min((gpu[2] for gpu in gpus), default=0)


# --------------------------------------------------------------------------------- errors


def env_error(
    error: OSError, doing: str, *, missing: bool = False, reported: bool = False
) -> EnvError:
    """The environment error an `OSError` comes to.

    Args:
      error: What was raised, here or on the machine the environment is on.
      doing: What was being done, which the message begins with.
      missing: Whether a path that is not there, or runs through a file, is the file not
        being there -- true of a read, not of a write.
      reported: Whether the machine reported it over a connection that therefore works, so
        that an errno of a broken connection is about something there -- a stale network
        mount, say -- rather than about the way there.

    Returns:
      `EnvConnectionError` for a broken connection, `EnvFileNotFound` for a missing path,
      `EnvPermissionDenied` for a refusal, and `EnvError` for anything else.
    """
    said = f"{doing}: {error.strerror or error}"
    number = error.errno
    if not reported and (isinstance(error, ConnectionError) or number in _CONNECTION):
        return EnvConnectionError(said)
    if number == errno.ENOENT or (missing and number == errno.ENOTDIR):
        return EnvFileNotFound(said)
    if isinstance(error, PermissionError) or number in _REFUSED:
        return EnvPermissionDenied(said)
    return EnvError(said)


def started_error(
    error: OSError, argv: Sequence[str], cwd: str, *, reported: bool = False
) -> EnvError:
    """The environment error a program that could not be started comes to.

    Args:
      error: Why it could not be.
      argv: The program and its arguments.
      cwd: Where it was to run: when that is what is missing, the workdir is gone and the
        environment is unavailable.
      reported: Whether the machine reported it, as :func:`env_error` takes it.

    Returns:
      `EnvUnavailable` for a workdir that is not there, and otherwise what
      :func:`env_error` makes of it.
    """
    if error.filename == cwd and error.errno in (errno.ENOENT, errno.ENOTDIR):
        return EnvUnavailable(f"the workdir {cwd} is not there")
    return env_error(error, f"could not run {argv[0]!r} in {cwd}", reported=reported)


def exit_status(returncode: int) -> int:
    """An exit status as a shell reports one: a death by signal N is 128 + N."""
    return 128 - returncode if returncode < 0 else returncode


def _shown(argv: Sequence[str] | str) -> str:
    """A command, short enough for a message."""
    said = f"the script {argv!r}" if isinstance(argv, str) else shlex.join(argv)
    return said if len(said) <= _SHOWN else f"{said[: _SHOWN - 3]}..."


# ------------------------------------------------------------------------------- the layout


def _readable(text: str, *, keep: int) -> str:
    """Some text as much of a directory name as it can be, with anything else a `-`."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip(".-")[:keep] or "x"


def _digest(text: str) -> str:
    """What tells two texts apart in a name, short."""
    return hashlib.blake2b(text.encode(), digest_size=6).hexdigest()


def home_of(state: PurePosixPath, source: PurePosixPath) -> PurePosixPath:
    """Where what is derived from one workdir lives.

    Args:
      state: Humanize's home on the machine.
      source: The workdir, absolute.

    Returns:
      `<state>/envs/<name>-<digest>`, named for the workdir's last part and its whole path.
    """
    name = _readable(source.name or "root", keep=32)
    return state / ENVS / f"{name}-{_digest(str(source))}"


def _named(id: str) -> str:  # noqa: A002 -- the flow API's name for it
    """The directory name an id is kept under: readable where it can be, unique always."""
    return f"{_readable(id, keep=40)}-{_digest(id)}"


def clone_dir(state: PurePosixPath, source: PurePosixPath, id: str) -> PurePosixPath:  # noqa: A002
    """Where the temporary copy of a workdir under an id lives."""
    return home_of(state, source) / "clones" / _named(id)


def scratch_dir(state: PurePosixPath, source: PurePosixPath, id: str) -> PurePosixPath:  # noqa: A002
    """Where the scratch directory derived from a workdir under an id lives."""
    return home_of(state, source) / "scratch" / _named(id)


def worktree_dir(
    state: PurePosixPath, source: PurePosixPath, ref: str | None
) -> PurePosixPath:
    """A fresh place for a worktree added from a workdir with no `dir` of its own."""
    readable = _readable(ref or "head", keep=32)
    return home_of(state, source) / "worktrees" / f"{readable}-{secrets.token_hex(4)}"


def _normal(path: PurePosixPath) -> PurePosixPath:
    """A path with its `.` and `..` taken out, as written rather than as the disk has it."""
    return PurePosixPath(posixpath.normpath(str(path)))


def tidy_workdir(workdir: PurePosixPath) -> PurePosixPath:
    """A workdir with its `.` and `..` taken out, so that one place has one name.

    Args:
      workdir: Absolute, or `~/...` under the home directory there.

    Returns:
      The same place, written plainly: `~/x/..` is `~`.

    Raises:
      EnvUnavailable: For one that is neither, or climbs out of the home directory it is
        under -- where that leads is not known until the machine says where home is.
    """
    if workdir.parts[:1] == ("~",):
        under = posixpath.normpath("/".join(workdir.parts[1:]) or ".")
        if under == ".." or under.startswith("../"):
            raise EnvUnavailable(
                f"{workdir} climbs out of the home directory it is under"
            )
        return PurePosixPath("~") if under == "." else PurePosixPath("~", under)
    if not workdir.is_absolute():
        raise EnvUnavailable(f"{workdir} is neither absolute nor under ~")
    return _normal(workdir)


# ------------------------------------------------------------------------------ a machine


class Running(Protocol):
    """One program started on a machine."""

    async def finished(self) -> tuple[int, bytes, bytes]:
        """Waits for it to end, and answers its exit status, stdout and stderr.

        Cancelling the wait leaves the program running; :meth:`kill` stops it, and ends
        this wait too, whoever is in it, however long the program takes to go.

        Raises:
          EnvError: The leaf for why it could not be run to its end, or that it was killed
            and could not be seen to end.
        """
        ...

    async def kill(self) -> None:
        """Kills it and everything it started, and waits a while for them to be gone.

        Bounded however the machine answers, and never raises: a program that already
        ended is let be.
        """
        ...

    def release(self) -> None:
        """Lets go of what was held to run it. Called once, after it is over or killed."""
        ...


class Claim(Protocol):
    """A hold on a temporary copy that other processes on the machine can see."""

    def release(self, *, forget: bool) -> None:
        """Lets go of it.

        Args:
          forget: Whether the copy is gone, so that what marked the hold can go too.
        """
        ...


class Machine(ABC):
    """What a driver does its work on: one machine, one connection to it, shared.

    One per driver made by :func:`~hmz.runtime.flowing.environments.open_env` or
    :func:`~hmz.runtime.flowing.environments.local_env`, and shared by everything derived
    from it. Paths handed to its methods are absolute on the machine, less a leading `~`
    that :meth:`absolute` resolves.

    Attributes:
      backend: Which kind of machine.
      provider: Which one of that kind: the ssh host, or "".
      identity: What tells this machine from others for as long as this process runs.
      running: Every command running on it, through any of its drivers or its own.
      holding: The temporary copies held through it, by key.
      closed: Whether the root driver was closed, after which nothing more is done here.
    """

    backend: EnvBackendKind
    provider: str
    identity: str

    def __init__(self) -> None:
        """Initializes a machine nothing has been done on."""
        self.running: set[_Command] = set()
        self.holding: set[tuple[str, str]] = set()
        self.closed = False

    # --- what is known without asking

    @abstractmethod
    def resources(self, *, gpus: bool) -> Resources:
        """What it has, as last seen; never waits on the network.

        Args:
          gpus: Whether the GPUs are asked about, which may be the one thing not yet known
            and dear to learn; without, what is said of them may be nothing.
        """

    @abstractmethod
    def available(self, workdir: PurePosixPath, *, seen: bool | None) -> bool:
        """Whether a workdir on it can be used, as last seen; never waits on the network.

        Args:
          workdir: The workdir.
          seen: Whether the driver at it last found it there, or None if it has not looked.
        """

    @abstractmethod
    def placement(self, workdir: PurePosixPath) -> Placement:
        """Where an agent session working in a workdir on it is put."""

    # --- what it takes asking

    @abstractmethod
    async def probe(self) -> None:
        """Reaches the machine, and learns what it has, where this has not yet.

        Raises:
          EnvUnavailable: If there is no such machine.
          EnvConnectionError: If it could not be reached.
        """

    @abstractmethod
    async def absolute(self, path: PurePosixPath) -> PurePosixPath:
        """A path with a leading `~` resolved to the home directory there."""

    @abstractmethod
    async def state(self) -> PurePosixPath:
        """Humanize's home on the machine, absolute: where derived directories live."""

    @abstractmethod
    async def start(self, argv: Sequence[str], cwd: PurePosixPath) -> Running:
        """Starts a program, with nothing on its stdin, in a process group of its own.

        Raises:
          EnvError: The leaf for why it could not be started; `EnvUnavailable` for a `cwd`
            that is not there.
        """

    @abstractmethod
    async def read(self, path: PurePosixPath) -> bytes:
        """What a file holds.

        Raises:
          EnvFileNotFound: If it is not there.
          EnvPermissionDenied: If it may not be read.
          EnvError: For anything else, like a directory.
        """

    @abstractmethod
    async def write(self, path: PurePosixPath, data: bytes) -> None:
        """Replaces a file whole, atomically, making the directories above it.

        Raises:
          EnvPermissionDenied: If it may not be written.
          EnvError: For anything else.
        """

    @abstractmethod
    async def mkdir(self, path: PurePosixPath) -> None:
        """Makes a directory and those above it; one already there is left as it is.

        Raises:
          EnvError: The leaf for why it could not be made.
        """

    @abstractmethod
    async def is_dir(self, path: PurePosixPath) -> bool:
        """Whether a directory is there, following links.

        Raises:
          EnvConnectionError: If the machine could not be asked.
        """

    async def claim(self, path: PurePosixPath) -> Claim | None:
        """Holds a temporary copy against other processes on the machine.

        None where the machine cannot: holds are then this process's alone.

        Raises:
          TempCloneBusy: If another process holds it.
        """
        del path
        return None

    async def run(
        self, argv: Sequence[str], cwd: PurePosixPath
    ) -> tuple[int, str, str]:
        """Runs a program to its end, and answers its status, stdout and stderr.

        Raises:
          EnvError: The leaf for why it could not be run.
        """
        running = await self.start(argv, cwd)
        held = _Command(running)
        self.running.add(held)
        try:
            await _unless_closed(self, held)
            status, out, err = await running.finished()
        except BaseException:
            await running.kill()
            raise
        finally:
            self.running.discard(held)
            running.release()
        if held.closing:
            raise EnvError(f"{_shown(argv)} was killed: its environment was closed")
        return status, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    async def remove(self, path: PurePosixPath) -> None:
        """Removes a tree; one that is not there is a no-op.

        Raises:
          EnvError: If it could not be removed.
        """
        status, _, err = await self.run(
            ["/bin/sh", "-c", REMOVE_SCRIPT, "humanize", str(path)], PurePosixPath("/")
        )
        if status:
            raise EnvError(
                f"could not remove {path}: {err.strip() or f'exit {status}'}"
            )

    async def clone(self, source: PurePosixPath, target: PurePosixPath) -> None:
        """Copies a tree to where it is not, or finds the copy already made there.

        Raises:
          EnvError: If it could not be copied.
        """
        status, _, err = await self.run(
            ["/bin/sh", "-c", CLONE_SCRIPT, "humanize", str(source), str(target)],
            PurePosixPath("/"),
        )
        if status:
            raise EnvError(
                f"could not copy {source} to {target}: {err.strip() or f'exit {status}'}"
            )

    async def worktree(
        self, source: PurePosixPath, target: PurePosixPath, ref: str | None
    ) -> None:
        """Adds a worktree of the repository a directory is in, detached.

        Raises:
          WorktreeError: With what git said, if it would not.
        """
        with contextlib.suppress(EnvError):
            await self.mkdir(target.parent)
        argv = ["git", "-C", str(source), "worktree", "add", "--quiet", "--detach"]
        argv += [str(target), *([ref] if ref is not None else [])]
        try:
            status, out, err = await self.run(argv, PurePosixPath("/"))
        except EnvFileNotFound as missing:
            raise WorktreeError(f"git is not installed: {missing}") from None
        if status:
            said = (err.strip() or out.strip() or f"exit {status}").splitlines()
            raise WorktreeError(f"git worktree add {target}: {' '.join(said)}")

    async def close(self) -> None:  # noqa: B027 -- nothing to let go of, by default
        """Lets go of the connection, if there is one. Idempotent."""


# --------------------------------------------------------------------------------- holds


@dataclass(slots=True, eq=False)
class _Held:
    """One temporary copy held in this process: who holds it, and through which machine."""

    holder: object
    machine: Machine
    claim: Claim | None


#: Every temporary copy held in this process, by machine and place. Process-wide rather than
#: per driver, because two runs in one process deriving one id from one workdir would
#: otherwise both be handed the one directory the id names.
_HELD: dict[tuple[str, str], _Held] = {}

#: Guards `_HELD` and `_LOCKS` against loops on other threads.
_GUARD = threading.Lock()

#: One lock per place and loop, alive only while somebody holds a reference to it -- which
#: is while they are making or removing what is there.
_LOCKS: weakref.WeakValueDictionary[tuple[object, str, str], asyncio.Lock] = (
    weakref.WeakValueDictionary()
)


def _lock(key: tuple[str, str]) -> asyncio.Lock:
    """The lock making and removing what is at one place goes under, on this loop."""
    loop = asyncio.get_running_loop()
    with _GUARD:
        lock = _LOCKS.get((loop, *key))
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[(loop, *key)] = lock
    return lock


def _busy(key: tuple[str, str], holder: object, target: PurePosixPath) -> _Held | None:
    """Who holds a place, refusing a holder that is not them.

    Raises:
      TempCloneBusy: If somebody else does.
    """
    with _GUARD:
        held = _HELD.get(key)
    if held is not None and held.holder != holder:
        raise TempCloneBusy(f"the temporary copy at {target} is held by another env")
    return held


def _let_go(machine: Machine) -> None:
    """Lets go of every temporary copy held through one machine, leaving them on disk."""
    for key in list(machine.holding):
        with _GUARD:
            held = _HELD.get(key)
            if held is not None and held.machine is machine:
                del _HELD[key]
            else:
                held = None
        if held is not None and held.claim is not None:
            held.claim.release(forget=False)
    machine.holding.clear()


# -------------------------------------------------------------------------------- driver


@dataclass(slots=True, eq=False)
class _Command:
    """A command a driver is running, and whether its driver was closed under it."""

    running: Running
    closing: bool = False


async def _unless_closed(machine: Machine, held: _Command) -> None:
    """Kills a command that was being started while its machine was closed.

    Closing kills what is running as it closes, and one still starting then was not among
    it; it is found here, once it is registered, and killed the same way.
    """
    if machine.closed:
        held.closing = True
        await held.running.kill()


def _limit(timeout: float) -> float | None:
    """A command's timeout as `asyncio.timeout` takes one: None for no limit.

    Raises:
      ValueError: For one that is negative or not a number.
    """
    if timeout != timeout or timeout < 0:  # noqa: PLR0124 -- NaN is the one unequal to itself
        raise ValueError(
            f"a timeout is 0 for none or a number of seconds, not {timeout}"
        )
    return None if timeout in (0, float("inf")) else timeout


class MachineEnvDriver:
    """A working directory on a machine: the :class:`~hmz.runtime.flowing.spi.EnvDriver`.

    One is made per `-e`, and per workspace for a `LocalEnv`, by
    :mod:`hmz.runtime.flowing.environments` -- that one is the root -- and every one derived
    from it shares its machine. Closing the root closes everything under it: the commands
    of every driver derived from it, the holds taken through them, and the connection.
    Closing a derived one stops its own commands.
    """

    __slots__ = ("_machine", "_root", "_running", "_seen", "_workdir")

    def __init__(
        self,
        machine: Machine,
        workdir: PurePosixPath,
        *,
        root: bool = True,
        seen: bool | None = None,
    ) -> None:
        """Initializes a driver at a workdir, doing nothing on the machine.

        Args:
          machine: The machine.
          workdir: The directory: absolute, or `~/...` under the home directory there.
          root: Whether this driver is the one the others are derived from.
          seen: Whether the workdir is known to be there.
        """
        self._machine = machine
        self._workdir = workdir
        self._root = root
        self._running: set[_Command] = set()
        self._seen = seen

    def __repr__(self) -> str:
        where = f"{self._machine.provider}:" if self._machine.provider else ""
        return f"<{type(self).__name__} {self._machine.backend}@{where}{self._workdir}>"

    # --- what it says about itself

    @property
    def backend(self) -> EnvBackendKind:
        return self._machine.backend

    @property
    def provider(self) -> str:
        """The ssh host, or "" for this machine."""
        return self._machine.provider

    @property
    def workdir(self) -> PurePosixPath:
        """Absolute, or `~/...` under the home of whoever ssh logs in as."""
        return self._workdir

    @property
    def capabilities(self) -> frozenset[type]:
        """Every environment mixin: both backends serve all of them."""
        return ENV_CAPABILITIES

    @property
    def cpu_count(self) -> int:
        """Logical CPUs of the machine, as last probed; 1 before an ssh machine is."""
        return self._machine.resources(gpus=False).cpu_count

    @property
    def memory(self) -> int:
        """Memory of the machine in bytes, as last probed; 0 before an ssh machine is."""
        return self._machine.resources(gpus=False).memory

    @property
    def gpu_count(self) -> int:
        """GPUs a command started here sees, as last probed; 0 before an ssh machine is.

        On this machine the first ask runs `nvidia-smi` where :meth:`probe` has not.
        """
        return self._machine.resources(gpus=True).gpu_count

    @property
    def gpu_memory(self) -> int:
        """Memory of the smallest of them, in bytes; 0 with none."""
        return self._machine.resources(gpus=True).gpu_memory

    @property
    def available(self) -> bool:
        """Whether the machine was reachable and the workdir there, as last seen.

        For this machine that is looked at now, which is one `stat`. For one over ssh it is
        what the last thing done there found: False until something has been -- which
        :meth:`probe` is for -- and False again once the connection broke or a command found
        the workdir gone. False for good once the root driver is closed.
        """
        machine = self._machine
        return not machine.closed and machine.available(self._workdir, seen=self._seen)

    def _open(self) -> Machine:
        """The machine, while it may still be asked for something.

        Raises:
          EnvError: Once the root driver is closed: its connection is gone, and nothing
            would close one made again.
        """
        machine = self._machine
        if machine.closed:
            raise EnvError(f"the environment at {self._workdir} is closed")
        return machine

    def placement(self) -> Placement:
        """Where an agent session working here is put."""
        return self._machine.placement(self._workdir)

    async def probe(self) -> None:
        """Reaches the machine, learns what it has, and checks the workdir is there.

        What makes `available` and the resources true before anything else has been done:
        cheap after the first time, and never blocking the loop.

        Raises:
          EnvUnavailable: If there is no such machine, or no such workdir on it.
          EnvConnectionError: If the machine could not be reached.
        """
        machine = self._open()
        await machine.probe()
        workdir = await machine.absolute(self._workdir)
        self._seen = await machine.is_dir(workdir)
        if not self._seen:
            raise EnvUnavailable(f"the workdir {self._workdir} is not there")

    # --- commands

    async def exec(
        self,
        argv: Sequence[str] | str,
        *,
        timeout: float,  # noqa: ASYNC109 -- the command's, enforced by killing it
    ) -> tuple[int, str, str]:
        """Runs a program, or a bash script given as a string, in the workdir.

        The program runs in a process group of its own with nothing on its stdin, and a
        timeout, a cancellation or closing the driver kills the whole group.

        Args:
          argv: The program and its arguments, run with no shell; or a script, run by bash.
          timeout: Seconds it may take, or 0 for no limit.

        Returns:
          The exit status -- 128 + N for one killed by signal N -- stdout and stderr, decoded
          as UTF-8 with errors replaced.

        Raises:
          ValueError: For an empty argv or a negative timeout.
          EnvCommandTimeout: If it ran past `timeout`. It and its children were killed.
          EnvUnavailable: If the workdir is not there.
          EnvError: The leaf for why it could not be run, or that the driver was closed.
          asyncio.CancelledError: If the awaiting task was cancelled. It was killed.
        """
        command = ["bash", "-c", argv] if isinstance(argv, str) else list(argv)
        if not command:
            raise ValueError("a command to run is at least a program")
        limit = _limit(timeout)
        machine = self._open()
        cwd = await machine.absolute(self._workdir)
        try:
            running = await machine.start(command, cwd)
        except EnvUnavailable:
            self._seen = False
            raise
        held = _Command(running)
        self._running.add(held)
        machine.running.add(held)
        try:
            await _unless_closed(machine, held)
            status, out, err = await self._waited(held, limit, argv, timeout)
        except EnvUnavailable:
            self._seen = False
            raise
        finally:
            self._running.discard(held)
            machine.running.discard(held)
            running.release()
        self._seen = True
        return status, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

    async def _waited(
        self,
        held: _Command,
        limit: float | None,
        argv: Sequence[str] | str,
        timeout: float,  # noqa: ASYNC109 -- what the caller asked for, for the message
    ) -> tuple[int, bytes, bytes]:
        """Waits for a command, killing it for its timeout or its caller's cancellation."""
        deadline = asyncio.timeout(limit)
        try:
            async with deadline:
                said = await held.running.finished()
        except BaseException as error:
            await held.running.kill()
            if isinstance(error, TimeoutError) and deadline.expired():
                raise EnvCommandTimeout(
                    f"{_shown(argv)} ran past its timeout of {timeout:g}s in "
                    f"{self._workdir}, and was killed"
                ) from None
            if isinstance(error, EnvError) and held.closing:
                raise EnvError(
                    f"{_shown(argv)} was killed: its environment was closed"
                ) from None
            raise
        if held.closing:
            raise EnvError(f"{_shown(argv)} was killed: its environment was closed")
        return said

    # --- files

    def _at(self, path: str | PurePosixPath) -> PurePosixPath:
        """A path as given to a driver: relative to the workdir, absolute, or `~/...`."""
        at = PurePosixPath(path)
        if at.is_absolute() or (at.parts and at.parts[0] == "~"):
            return at
        return self._workdir / at

    async def read(self, path: str) -> bytes:
        """What a file holds.

        Args:
          path: The file, relative to the workdir, absolute, or `~/...`.

        Raises:
          EnvFileNotFound: If it is not there.
          EnvPermissionDenied: If it may not be read.
          EnvError: For anything else, like a directory.
        """
        machine = self._open()
        return await machine.read(await machine.absolute(self._at(path)))

    async def write(self, path: str, data: bytes) -> None:
        """Replaces a file whole, atomically, making the directories above it.

        Args:
          path: The file, relative to the workdir, absolute, or `~/...`.
          data: What it holds afterwards.

        Raises:
          EnvPermissionDenied: If it may not be written.
          EnvError: For anything else, like a directory in its place.
        """
        machine = self._open()
        await machine.write(await machine.absolute(self._at(path)), bytes(data))

    # --- deriving

    def _derived(self, workdir: PurePosixPath) -> MachineEnvDriver:
        """A driver at another workdir on this machine, known to be there."""
        return MachineEnvDriver(self._machine, workdir, root=False, seen=True)

    async def derive_subdir(self, subdir: PurePosixPath | str) -> MachineEnvDriver:
        """A driver at a directory under this workdir, made if missing.

        Args:
          subdir: Where, relative to the workdir; `.` and `..` are taken as written.

        Raises:
          ValueError: If `subdir` is absolute or climbs out of the workdir.
          EnvError: If it could not be made.
        """
        under = _normal(PurePosixPath(subdir))
        if under.is_absolute() or under.parts[:1] == ("..",):
            raise ValueError(
                f"{str(subdir)!r} is not a directory under {self._workdir}"
            )
        workdir = self._workdir / under
        machine = self._open()
        await machine.mkdir(await machine.absolute(workdir))
        return self._derived(workdir)

    async def derive_worktree(
        self,
        *,
        ref: str | None,
        dir: PurePosixPath | str | None,  # noqa: A002 -- the flow API's name for it
    ) -> MachineEnvDriver:
        """A driver at a new git worktree of the repository the workdir is in.

        Args:
          ref: What to check out, detached; None for the workdir's `HEAD`.
          dir: Where, relative to the workdir, absolute, or `~/...`; None for a fresh
            directory under `envs/` in humanize's home on the machine.

        Raises:
          WorktreeError: Not a repository, an unknown ref, or a directory that is taken,
            with what git said.
        """
        if ref is not None and (not ref.strip() or ref.startswith("-")):
            raise WorktreeError(f"{ref!r} is not a ref to check out")
        machine = self._open()
        source = await machine.absolute(self._workdir)
        if dir is None:
            target = worktree_dir(await machine.state(), source, ref)
        else:
            target = _normal(await machine.absolute(self._at(dir)))
        await machine.worktree(source, target, ref)
        return self._derived(target)

    async def derive_temp_clone(
        self,
        id: str,  # noqa: A002 -- the flow API's name for it
        *,
        holder: object,
    ) -> MachineEnvDriver:
        """A driver at a temporary copy of the workdir.

        The copy lives at a place named for this workdir and the id, so a resumed run finds
        it. The first call for an id makes it -- or finds it left there -- and gives it to
        `holder`; later calls by an equal holder answer the same copy, and calls by any other
        raise, as does a call while another process on this machine holds it.

        Raises:
          TempCloneBusy: If another holder holds the id.
          EnvError: If the copy could not be made.
        """
        machine = self._open()
        source = await machine.absolute(self._workdir)
        target = clone_dir(await machine.state(), source, id)
        if target.is_relative_to(source):
            raise EnvError(
                f"a temporary copy of {source} would be made inside it, at {target}: "
                "humanize's home is under the workdir"
            )
        key = (machine.identity, str(target))
        # Asked first so that another holder is refused at once rather than after the copy
        # being made for the first one; asked again under the lock, where the copy is whole.
        _busy(key, holder, target)
        async with _lock(key):
            self._open()
            if _busy(key, holder, target) is not None:
                return self._derived(target)
            claim = await machine.claim(target)
            held = _Held(holder, machine, claim)
            with _GUARD:
                _HELD[key] = held
            machine.holding.add(key)
            try:
                await machine.clone(source, target)
            except BaseException:
                with _GUARD:
                    if _HELD.get(key) is held:
                        del _HELD[key]
                machine.holding.discard(key)
                if claim is not None:
                    claim.release(forget=False)
                raise
        return self._derived(target)

    async def destroy_temp_clone(self, id: str) -> None:  # noqa: A002 -- the flow API's
        """Removes a copy and frees its id, whoever in this process holds it.

        A no-op for an id with no copy, and for one another process on this machine holds.

        Raises:
          EnvError: If it could not be removed.
        """
        machine = self._open()
        source = await machine.absolute(self._workdir)
        target = clone_dir(await machine.state(), source, id)
        key = (machine.identity, str(target))
        async with _lock(key):
            self._open()
            with _GUARD:
                held = _HELD.pop(key, None)
            if held is not None:
                held.machine.holding.discard(key)
                claim = held.claim
            elif not await machine.is_dir(target):
                return
            else:
                try:
                    claim = await machine.claim(target)
                except TempCloneBusy:
                    log.info("left %s alone: another process holds it", target)
                    return
            try:
                await machine.remove(target)
            except BaseException:
                if claim is not None:
                    claim.release(forget=False)
                raise
            if claim is not None:
                claim.release(forget=True)

    async def derive_scratch(self, id: str) -> MachineEnvDriver:  # noqa: A002 -- the API's
        """A driver at an empty directory on the same machine, the same one for the same id.

        Raises:
          ScratchError: If it could not be made.
        """
        machine = self._open()
        source = await machine.absolute(self._workdir)
        target = scratch_dir(await machine.state(), source, id)
        async with _lock((machine.identity, str(target))):
            self._open()
            try:
                await machine.mkdir(target)
            except EnvConnectionError:
                raise
            except EnvError as error:
                raise ScratchError(f"could not make {target}: {error}") from None
        return self._derived(target)

    async def destroy_scratch(self, id: str) -> None:  # noqa: A002 -- the flow API's
        """Removes a scratch directory. A no-op for an unknown id.

        Raises:
          ScratchError: If it could not be removed.
        """
        machine = self._open()
        source = await machine.absolute(self._workdir)
        target = scratch_dir(await machine.state(), source, id)
        async with _lock((machine.identity, str(target))):
            self._open()
            try:
                await machine.remove(target)
            except EnvConnectionError:
                raise
            except EnvError as error:
                raise ScratchError(f"could not remove {target}: {error}") from None

    # --- letting go

    async def close(self) -> None:
        """Stops this driver's commands; the root's also lets go of the machine. Idempotent.

        Temporary copies and scratch directories stay where they are: removing them is the
        engine's, for the flows that are not resumable, and done before this. The holds on
        copies taken through the root are let go of, so that a run resumed in this process
        can take them again -- once the copying and removing in flight is stopped, so that
        nobody else takes a copy half made. A command stopped this way raises `EnvError` to
        whoever was waiting on it. Closing the root is final: every driver of its machine
        refuses what it is asked afterwards, and is not `available`.
        """
        machine = self._machine
        if self._root:
            machine.closed = True
        commands = list(machine.running if self._root else self._running)
        for command in commands:
            command.closing = True
        if commands:
            await asyncio.gather(*(command.running.kill() for command in commands))
        if self._root:
            _let_go(machine)
            await machine.close()
