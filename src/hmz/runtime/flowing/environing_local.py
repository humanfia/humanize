"""This machine, as an environment driver does its work on it.

Commands are the event loop's own subprocesses, each in a process group of its own so that
a timeout kills everything it started. Files are read and written by this process on a
worker thread -- no process per read -- and written atomically. What the machine has is read
once per process: CPUs and memory from the kernel, as they are asked for, and GPUs from
`nvidia-smi`, which :meth:`LocalMachine.probe` runs off the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import os
import secrets
import shutil
import signal
import stat
import subprocess
import threading
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from hmz import home
from hmz.flows import EnvBackendKind, EnvError, TempCloneBusy

from .environing import (
    GPU_QUERY,
    KILLED_WITHIN,
    Machine,
    Resources,
    env_error,
    exit_status,
    gpus_of,
    started_error,
)
from .spi import Placement

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["LocalMachine"]

#: How long `nvidia-smi` is given to say what GPUs there are.
_GPU_WITHIN = 30.0

#: What this machine has, read once per process: CPUs and memory, then GPUs.
_cpus_memory: tuple[int, int] | None = None
_gpus: tuple[int, int] | None = None
_READING = threading.Lock()


def _cpus_and_memory() -> tuple[int, int]:
    """CPUs this process may run on, and memory, read from the kernel once."""
    global _cpus_memory  # noqa: PLW0603 -- one machine, read once per process
    if _cpus_memory is None:
        import psutil

        try:
            cpus = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            cpus = os.cpu_count() or 1
        _cpus_memory = (max(cpus, 1), int(psutil.virtual_memory().total))
    return _cpus_memory


def _gpus_now() -> tuple[int, int]:
    """The GPUs a command started here sees, asking `nvidia-smi` the first time.

    Blocks for as long as `nvidia-smi` takes, once per process; :meth:`LocalMachine.probe`
    is what asks it off the loop.
    """
    global _gpus  # noqa: PLW0603 -- one machine, read once per process
    with _READING:
        if _gpus is None:
            _gpus = _asked_nvidia_smi()
        return _gpus


def _asked_nvidia_smi() -> tuple[int, int]:
    """What `nvidia-smi` says, narrowed by `CUDA_VISIBLE_DEVICES`; none where it is not."""
    if shutil.which(GPU_QUERY[0]) is None:
        return 0, 0
    try:
        said = subprocess.run(
            GPU_QUERY,
            capture_output=True,
            text=True,
            timeout=_GPU_WITHIN,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return 0, 0
    if said.returncode:
        return 0, 0
    return gpus_of(said.stdout.splitlines(), os.environ.get("CUDA_VISIBLE_DEVICES"))


# ------------------------------------------------------------------------------ commands


class _Collected(asyncio.SubprocessProtocol):
    """What one command wrote, and when it ended."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.out = bytearray()
        self.err = bytearray()
        #: Set when the process has exited.
        self.exited: asyncio.Future[None] = loop.create_future()
        #: Set when it has exited and both its pipes are closed: when all it wrote is here.
        self.closed: asyncio.Future[None] = loop.create_future()

    def pipe_data_received(self, fd: int, data: bytes | bytearray) -> None:
        (self.err if fd == 2 else self.out).extend(data)  # noqa: PLR2004 -- stderr

    def process_exited(self) -> None:
        if not self.exited.done():
            self.exited.set_result(None)

    def connection_lost(self, exc: Exception | None) -> None:
        del exc
        if not self.closed.done():
            self.closed.set_result(None)


class _LocalRun:
    """One command running here."""

    __slots__ = ("_collected", "_gave_up", "_killing", "_pid", "_transport")

    def __init__(
        self, transport: asyncio.SubprocessTransport, collected: _Collected
    ) -> None:
        self._transport = transport
        self._collected = collected
        self._pid = transport.get_pid()
        #: Set once it was killed and waited for, whether or not it could be seen to end.
        self._gave_up: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        #: The one killing of it, however many ask for it.
        self._killing: asyncio.Task[None] | None = None

    async def finished(self) -> tuple[int, bytes, bytes]:
        # Neither future is cancelled by a cancelled wait: `kill` goes on waiting on one,
        # and sets the other.
        closed = self._collected.closed
        await asyncio.wait({closed, self._gave_up}, return_when=asyncio.FIRST_COMPLETED)
        if not closed.done():
            raise EnvError(
                f"process {self._pid} was killed, and was not seen to end within "
                f"{2 * KILLED_WITHIN:g}s"
            )
        returncode = self._transport.get_returncode()
        status = exit_status(returncode) if returncode is not None else 1
        return status, bytes(self._collected.out), bytes(self._collected.err)

    async def kill(self) -> None:
        # Once, and waited on by everyone who asks -- and not cancelled with any of them.
        if self._killing is None:
            self._killing = asyncio.ensure_future(self._kill())
        await asyncio.shield(self._killing)

    async def _kill(self) -> None:
        collected = self._collected
        # The whole group, which is everything it started that did not leave it -- and so
        # also once it has exited itself, while what it left behind holds its output open.
        # Once it has been reaped its number is free, and a group of that number is ours
        # only while no process has the number again: a group is only ever made with its
        # leader's number, so another group of it means another process holding it.
        if not collected.closed.done() and (
            not collected.exited.done() or not _taken(self._pid)
        ):
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(self._pid, signal.SIGKILL)
        await asyncio.wait({collected.exited}, timeout=KILLED_WITHIN)
        # What still holds its output open left its group -- a daemon that called setsid --
        # and is not waited on: its pipes are let go of here, which is what ends the wait.
        self._transport.close()
        await asyncio.wait({collected.closed}, timeout=KILLED_WITHIN)
        if not self._gave_up.done():
            self._gave_up.set_result(None)

    def release(self) -> None:
        self._transport.close()


# ---------------------------------------------------------------------------------- holds


class _Claim:
    """A lock file held with `flock`, which the kernel lets go of if this process dies."""

    __slots__ = ("_fd", "_path")

    def __init__(self, fd: int, path: Path) -> None:
        self._fd = fd
        self._path = path

    def release(self, *, forget: bool) -> None:
        if self._fd < 0:
            return
        if forget:
            # Unlinked while it is still held, so that nobody can lock the name in between;
            # whoever opened it before it went finds, once they hold it, that it is not the
            # file the name is, and opens the name again.
            with contextlib.suppress(OSError):
                self._path.unlink()
        os.close(self._fd)
        self._fd = -1


def _claimed(path: Path) -> _Claim:
    """Holds the lock file beside a temporary copy.

    Raises:
      TempCloneBusy: If another process holds it.
      OSError: If it could not be made.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise TempCloneBusy(
                f"the temporary copy beside {path} is held by another process"
            ) from None
        except BaseException:
            os.close(fd)
            raise
        held = os.fstat(fd)
        try:
            there = path.stat()
        except FileNotFoundError:
            there = None
        if there is not None and (there.st_dev, there.st_ino) == (
            held.st_dev,
            held.st_ino,
        ):
            return _Claim(fd, path)
        os.close(fd)


# ---------------------------------------------------------------------------------- files


def _written(path: Path, data: bytes) -> None:
    """Replaces a file whole: written beside it and renamed over it, with its mode kept."""
    if path.is_symlink():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{secrets.token_hex(6)}.hmz-tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o666)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        with contextlib.suppress(FileNotFoundError):
            temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        temporary.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise


def _opened_up(top: Path) -> None:
    """Makes every directory of a tree one its owner may list, enter and write in.

    Top-down, so that each is opened before it is looked into. Never through a link, whose
    mode is the mode of whatever it points to outside the tree.
    """
    top.chmod(top.lstat().st_mode | stat.S_IRWXU)
    for at, directories, _ in top.walk():
        for name in directories:
            one = at / name
            mode = one.lstat().st_mode
            if stat.S_ISDIR(mode):
                one.chmod(mode | stat.S_IRWXU)


def _removed(path: Path) -> None:
    """Removes a tree, making writable what stands in the way. Missing is a no-op."""
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    # Out of its place first, as `REMOVE_SCRIPT` says why -- ending in this process's number,
    # which is what the next copy made beside it reads to sweep it once this is gone.
    gone = path.with_name(f"{path.name}.part.gone.{secrets.token_hex(4)}.{os.getpid()}")
    try:
        path.rename(gone)
    except FileNotFoundError:
        return
    try:
        shutil.rmtree(gone)
    except PermissionError:
        # A directory in it nobody may write into, or list: a read-only module cache.
        _opened_up(gone)
        shutil.rmtree(gone)


def _is_dir(path: Path) -> bool:
    return path.is_dir()


def _taken(pid: int) -> bool:
    """Whether a process has this number now, whoever's it is."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


# -------------------------------------------------------------------------------- machine


class LocalMachine(Machine):
    """This machine."""

    backend = EnvBackendKind.LOCAL
    provider = ""
    identity = "local"

    def resources(self, *, gpus: bool) -> Resources:
        """What this machine has; the first ask for GPUs runs `nvidia-smi` if not probed."""
        cpus, memory = _cpus_and_memory()
        count, least = _gpus_now() if gpus else (0, 0)
        return Resources(cpus, memory, count, least)

    def available(self, workdir: PurePosixPath, *, seen: bool | None) -> bool:
        """Whether the workdir is a directory, looked at now."""
        del seen
        return _local(self._home(workdir)).is_dir()

    def placement(self, workdir: PurePosixPath) -> Placement:
        return Placement(EnvBackendKind.LOCAL, "", workdir, None)

    async def probe(self) -> None:
        if _gpus is None:
            await asyncio.to_thread(_gpus_now)
        _cpus_and_memory()

    @staticmethod
    def _home(path: PurePosixPath) -> PurePosixPath:
        """A path with a leading `~` resolved to this user's home."""
        if path.parts[:1] == ("~",):
            return PurePosixPath(Path.home(), *path.parts[1:])
        return path

    async def absolute(self, path: PurePosixPath) -> PurePosixPath:
        return self._home(path)

    async def state(self) -> PurePosixPath:
        return PurePosixPath(home().absolute())

    async def start(self, argv: Sequence[str], cwd: PurePosixPath) -> _LocalRun:
        loop = asyncio.get_running_loop()
        try:
            transport, collected = await loop.subprocess_exec(
                lambda: _Collected(loop),
                *argv,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            raise started_error(error, argv, str(cwd)) from error
        return _LocalRun(transport, collected)

    async def read(self, path: PurePosixPath) -> bytes:
        try:
            return await asyncio.to_thread(_local(path).read_bytes)
        except OSError as error:
            raise env_error(error, f"could not read {path}", missing=True) from error

    async def write(self, path: PurePosixPath, data: bytes) -> None:
        try:
            await asyncio.to_thread(_written, _local(path), data)
        except OSError as error:
            raise env_error(error, f"could not write {path}") from error

    async def mkdir(self, path: PurePosixPath) -> None:
        try:
            await asyncio.to_thread(_local(path).mkdir, parents=True, exist_ok=True)
        except OSError as error:
            raise env_error(error, f"could not make the directory {path}") from error

    async def is_dir(self, path: PurePosixPath) -> bool:
        return await asyncio.to_thread(_is_dir, _local(path))

    async def remove(self, path: PurePosixPath) -> None:
        try:
            await asyncio.to_thread(_removed, _local(path))
        except OSError as error:
            raise env_error(error, f"could not remove {path}") from error

    async def claim(self, path: PurePosixPath) -> _Claim:
        lock = _local(path)
        try:
            return _claimed(lock.with_name(f"{lock.name}.lock"))
        except OSError as error:
            raise EnvError(f"could not hold {path}: {error}") from error


def _local(path: PurePosixPath) -> Path:
    """A path on this machine."""
    return Path(path)
