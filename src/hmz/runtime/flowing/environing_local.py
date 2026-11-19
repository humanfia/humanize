"""This machine, as an environment driver does its work on it.

Commands are the event loop's own subprocesses, each in a process group of its own so that
a timeout kills everything it started; a terminal is a pty `ptyprocess` forks, which the
loop reads and writes as the kernel says it can. Files are read, written and listed by
this process on a worker thread -- no process per read -- and written atomically. What the
machine has is read once per process: CPUs and memory from the kernel, as they are asked
for, and GPUs from `nvidia-smi`, which :meth:`LocalMachine.probe` runs off the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
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
from hmz.flows import EnvBackendKind, EnvError, EnvUnavailable, TempCloneBusy

from .environing import (
    GPU_QUERY,
    KILLED_WITHIN,
    TERM,
    Machine,
    Pty,
    Resources,
    env_error,
    exit_status,
    gpus_of,
    started_error,
)
from .spi import EnvEntry, Placement

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable, Sequence

    from ptyprocess import PtyProcess  # pyright: ignore[reportMissingTypeStubs]

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


# ------------------------------------------------------------------------------ terminals

#: The most one read of a terminal answers.
_READ = 1 << 16

#: The longest a terminal's end is waited between two looks for it.
_LOOKED_EVERY = 0.5

#: How often what a killed terminal still writes is dropped, until it has ended.
_DROPPED_EVERY = 0.01


def _spawned(
    argv: Sequence[str], cwd: PurePosixPath, cols: int, rows: int
) -> PtyProcess:
    """A program started on a pty, in a session of its own whose terminal that is.

    Raises:
      OSError: If it could not be: not found, not runnable, or `cwd` not there.
    """
    from ptyprocess import PtyProcess  # pyright: ignore[reportMissingTypeStubs]

    env = dict(os.environ)
    env["TERM"] = TERM
    for sized in ("COLUMNS", "LINES"):
        env.pop(sized, None)
    where = str(cwd)
    command = list(argv)
    if "/" in command[0] and not command[0].startswith("/"):
        # Looked for here, before the child is in `cwd`: a path is the workdir's.
        command[0] = os.path.join(where, command[0])  # noqa: PTH118 -- a string it takes
    try:
        # Into `cwd` before the program is run rather than by `ptyprocess`'s own `cwd`,
        # which would raise in the child it forked, where nobody catches it.
        return PtyProcess.spawn(  # pyright: ignore[reportUnknownMemberType]
            command,
            env=env,
            dimensions=(rows, cols),
            preexec_fn=lambda: os.chdir(where),
        )
    except FileNotFoundError as error:
        if error.errno is not None:
            raise
        # Not on the PATH, or `cwd` gone since it was looked at, which `ptyprocess` says
        # with no errno.
        gone = not os.path.isdir(where)  # noqa: PTH112 -- a string it takes
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), where if gone else argv[0]
        ) from error


def _session(leader: int) -> set[int]:
    """The process groups of every process in the session a terminal's program leads."""
    import psutil

    groups = {leader}
    for pid in psutil.pids():
        with contextlib.suppress(OSError):
            if os.getsid(pid) == leader:
                groups.add(os.getpgid(pid))
    return groups


class _LocalPty(Pty):
    """A program on a pty here, whose master the loop reads and writes when it can."""

    def __init__(self, process: PtyProcess) -> None:
        self._process = process
        # Let go of by `ptyprocess` without the pauses it would otherwise sleep through.
        process.delayafterclose = 0
        process.delayafterterminate = 0
        self._fd: int = process.fd
        self._pid: int = process.pid
        os.set_blocking(self._fd, False)
        self._loop = asyncio.get_running_loop()
        self._closed = False
        self._waiting: set[asyncio.Future[None]] = set()
        self._reading = asyncio.Lock()
        self._writing = asyncio.Lock()
        self._status: asyncio.Future[int] | None = None
        self._killing: asyncio.Future[None] | None = None

    async def _ready(
        self,
        watch: Callable[..., object],
        unwatch: Callable[[int], object],
    ) -> None:
        """Waits for the kernel to say the master can be read, or written; or for it to close."""
        ready: asyncio.Future[None] = self._loop.create_future()

        def able() -> None:
            if not ready.done():
                ready.set_result(None)

        self._waiting.add(ready)
        watch(self._fd, able)
        try:
            await ready
        finally:
            self._waiting.discard(ready)
            if not self._closed:
                unwatch(self._fd)

    async def read(self) -> bytes:
        async with self._reading:
            while not self._closed:
                try:
                    data = os.read(self._fd, _READ)
                except BlockingIOError:
                    await self._ready(self._loop.add_reader, self._loop.remove_reader)
                    continue
                except OSError as error:
                    # Linux says the far end has gone with EIO, where macOS ends the file.
                    if error.errno != errno.EIO:
                        raise env_error(error, "could not read a terminal") from error
                    data = b""
                if not data:
                    self._close()
                return data
            return b""

    async def write(self, data: bytes) -> None:
        async with self._writing:
            left = memoryview(data)
            while left and not self._closed:
                try:
                    wrote = os.write(self._fd, left)
                except BlockingIOError:
                    await self._ready(self._loop.add_writer, self._loop.remove_writer)
                    continue
                except OSError:
                    return  # it has ended, and what is typed at it is dropped
                left = left[wrote:]

    async def resize(self, cols: int, rows: int) -> None:
        if not self._closed:
            with contextlib.suppress(OSError):
                self._process.setwinsize(rows, cols)  # pyright: ignore[reportUnknownMemberType]

    async def wait(self) -> int:
        if self._status is None:
            self._status = asyncio.ensure_future(self._reaped())
        return await asyncio.shield(self._status)

    async def _reaped(self) -> int:
        """Looks for it to have ended, more seldom the longer it runs, and reaps it."""
        import ptyprocess  # pyright: ignore[reportMissingTypeStubs]

        pause = 0.005
        while True:
            try:
                alive = self._process.isalive()
            except ptyprocess.PtyProcessError:
                return 1
            if not alive:
                break
            await asyncio.sleep(pause)
            pause = min(pause * 2, _LOOKED_EVERY)
        killed = self._process.signalstatus
        if killed is not None:
            return 128 + int(killed)
        return int(self._process.exitstatus or 0)

    async def kill(self) -> None:
        if self._killing is None:
            self._killing = asyncio.ensure_future(self._kill())
        await asyncio.shield(self._killing)

    async def _kill(self) -> None:
        status = self._status
        if status is None or not status.done():
            # Every group of its session: the program's, and those job control put each
            # job in, the foreground's and the background's -- while the program is not yet
            # reaped, so that the session's number cannot be another's.
            groups = {self._pid}
            with contextlib.suppress(OSError):
                groups = await asyncio.to_thread(_session, self._pid)
            for group in groups:
                if group > 0:
                    with contextlib.suppress(OSError):
                        os.killpg(group, signal.SIGKILL)
        # The master is kept until the kill has ended it: letting go hangs the terminal
        # up, and of a SIGKILL and a SIGHUP both pending macOS delivers the lower, so that
        # it would end by the hangup. What it wrote is read and dropped meanwhile, which
        # would otherwise hold up its exit: macOS waits for the terminal's output to drain.
        ended = asyncio.ensure_future(self.wait())
        try:
            async with asyncio.timeout(KILLED_WITHIN):
                while not ended.done():
                    self._drop()
                    await asyncio.wait({ended}, timeout=_DROPPED_EVERY)
        except TimeoutError:
            ended.cancel()
        self._close()

    def _drop(self) -> None:
        """Reads what the terminal has written and nobody has read, and drops it."""
        with contextlib.suppress(OSError):
            while not self._closed and os.read(self._fd, _READ):
                pass

    def _close(self) -> None:
        """Lets go of the master, waking whoever waits on it."""
        if self._closed:
            return
        self._closed = True
        self._loop.remove_reader(self._fd)
        self._loop.remove_writer(self._fd)
        for waiting in list(self._waiting):
            if not waiting.done():
                waiting.set_result(None)
        with contextlib.suppress(OSError):
            self._process.fileobj.close()
        self._process.closed = True

    def release(self) -> None:
        if self._status is not None and self._status.done():
            self._close()


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


def _entry(path: Path, name: str) -> EnvEntry:
    """What one path is, a final link not followed."""
    info = path.lstat()
    mode = info.st_mode
    target = None
    if stat.S_ISDIR(mode):
        kind = "dir"
    elif stat.S_ISLNK(mode):
        kind = "link"
        target = str(path.readlink())
    elif stat.S_ISREG(mode):
        kind = "file"
    else:
        kind = "other"
    return EnvEntry(name, kind, info.st_size, info.st_mtime_ns / 1e9, target)


def _listed(path: Path) -> builtins.list[EnvEntry]:
    """What a directory holds; what goes while it is looked at is left out."""
    entries: builtins.list[EnvEntry] = []
    with os.scandir(path) as listing:
        for one in listing:
            with contextlib.suppress(FileNotFoundError):
                entries.append(_entry(Path(one.path), one.name))
    return entries


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

    def __init__(self) -> None:
        """Initializes this machine, before anything has been looked for on it."""
        super().__init__()
        #: Which programs are on this process's PATH, by name, as each was first looked for.
        self._tools: dict[str, bool] = {}

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

    def has(self, tool: str) -> bool:
        """Whether a program is on this process's PATH, looked for the first time it is.

        Args:
          tool: The program.
        """
        found = self._tools.get(tool)
        if found is None:
            found = self._tools[tool] = shutil.which(tool) is not None
        return found

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
        # Started apart from whoever waits on it: cancelled while its pipes are still being
        # connected, the command already running, asyncio kills the command alone and leaves
        # what it started. So it finishes starting, and is then killed whole, as a command
        # cancelled once started is.
        starting = asyncio.ensure_future(
            loop.subprocess_exec(
                lambda: _Collected(loop),
                *argv,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        )
        try:
            transport, collected = await asyncio.shield(starting)
        except asyncio.CancelledError:
            with contextlib.suppress(OSError):
                run = _LocalRun(*await starting)
                await run.kill()
                run.release()
            raise
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

    async def list(self, path: PurePosixPath) -> builtins.list[EnvEntry]:
        try:
            return await asyncio.to_thread(_listed, _local(path))
        except OSError as error:
            raise env_error(error, f"could not list {path}") from error

    async def stat(self, path: PurePosixPath) -> EnvEntry:
        try:
            return await asyncio.to_thread(_entry, _local(path), path.name)
        except OSError as error:
            raise env_error(error, f"could not look at {path}", missing=True) from error

    async def rename(self, path: PurePosixPath, to: PurePosixPath) -> None:
        try:
            await asyncio.to_thread(os.rename, _local(path), _local(to))
        except OSError as error:
            raise env_error(error, f"could not move {path} to {to}") from error

    async def pty(
        self, argv: Sequence[str], cwd: PurePosixPath, *, cols: int, rows: int
    ) -> _LocalPty:
        if not await self.is_dir(cwd):
            raise EnvUnavailable(f"the workdir {cwd} is not there")
        try:
            process = await asyncio.to_thread(_spawned, argv, cwd, cols, rows)
        except OSError as error:
            raise started_error(error, argv, str(cwd)) from error
        return _LocalPty(process)

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
