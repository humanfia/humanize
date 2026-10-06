"""Stand-ins for what the environment and harness drivers stand on, for their unit tests.

- :class:`MemoryMachine` is a :class:`~hmz.runtime.flowing.environing.Machine` in memory:
  files and directories in dictionaries, and every program it is asked to start answered by a
  function -- the shell scripts the driver copies, removes and adds worktrees with among them.
- :class:`FakeRemote` stands for coganchor's `RemoteClient` at the far end of an ssh or a
  `docker exec`: it says what :data:`~hmz.runtime.flowing.environing_ssh.PROBE_SCRIPT` asks,
  answers commands from a function and keeps files in memory. :func:`reach` puts it where
  `hmz.coganchor.transport.connect` would have connected.
- :class:`Runtime` is a saved runtime of any backend, as `hmz.coganchor.machines.store` keeps
  one, and :class:`Held` a container a runtime already runs.
"""

from __future__ import annotations

import asyncio
import errno
import itertools
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

from hmz.flows import EnvBackendKind, EnvError, EnvUnavailable, TempCloneBusy
from hmz.runtime.flowing.environing import (
    CLONE_SCRIPT,
    REMOVE_SCRIPT,
    Claim,
    Machine,
    Resources,
)
from hmz.runtime.flowing.environing_ssh import PROBE_SCRIPT
from hmz.runtime.flowing.spi import Placement

if TYPE_CHECKING:
    import io
    from collections.abc import Callable, Mapping, Sequence

    import pytest

    from hmz.coganchor.transport import Endpoint

#: What a command answers: its status, stdout and stderr; or None to run until killed.
type Said = tuple[int, str, str] | None

_machines = itertools.count(1)


# ----------------------------------------------------------------------- a machine in memory


class ScriptedRun:
    """One program a :class:`MemoryMachine` started, answering what it was scripted to."""

    def __init__(self, said: Said) -> None:
        self.said = said
        self.killed = False
        self.released = 0
        self._gone = asyncio.Event()

    async def finished(self) -> tuple[int, bytes, bytes]:
        if self.said is None:
            await self._gone.wait()
            raise EnvError("killed")
        status, out, err = self.said
        return status, out.encode(), err.encode()

    async def kill(self) -> None:
        self.killed = True
        self._gone.set()

    def release(self) -> None:
        self.released += 1


class MemoryClaim:
    """A hold on a temporary copy, as a machine that can hold one across processes makes it."""

    def __init__(
        self, path: PurePosixPath, released: list[tuple[PurePosixPath, bool]]
    ) -> None:
        self.path = path
        self._released = released

    def release(self, *, forget: bool) -> None:
        self._released.append((self.path, forget))


class MemoryMachine(Machine):
    """A machine whose disk is two dictionaries; see the module docstring.

    Attributes:
      files: Every file, by absolute path.
      dirs: Every directory, by absolute path.
      started: Every program started, with where.
      runs: What each of those became, in the same order.
      answer: What answers a program that is none of the driver's own scripts.
      tools: Whether each program was seen on its PATH; one not in it was never looked for.
      probed: How many times it was probed.
      busy: Places another process on the machine holds.
      claims: Every hold let go of, and whether it was forgotten.
      broken: What starting a program raises, where it is not None.
    """

    def __init__(
        self,
        *,
        backend: EnvBackendKind = EnvBackendKind.LOCAL,
        provider: str = "",
        home: str = "/home/me",
        state: str = "/home/me/.hmz",
        dirs: Sequence[str] = ("/work",),
        claims: bool = False,
    ) -> None:
        super().__init__()
        self.backend = backend
        self.provider = provider
        self.identity = f"memory-{next(_machines)}"
        self.home = PurePosixPath(home)
        self.where = PurePosixPath(state)
        self.files: dict[PurePosixPath, bytes] = {}
        self.dirs: set[PurePosixPath] = {PurePosixPath("/"), *map(PurePosixPath, dirs)}
        self.started: list[tuple[tuple[str, ...], PurePosixPath]] = []
        self.runs: list[ScriptedRun] = []
        self.answer: Callable[[tuple[str, ...], PurePosixPath], Said] = _ok
        self.tools: dict[str, bool] = {}
        self.probed = 0
        self.busy: set[PurePosixPath] = set()
        self.claims: list[tuple[PurePosixPath, bool]] = []
        self.holds = claims
        self.broken: EnvError | None = None
        self.shut = 0

    # --- what is known without asking

    def resources(self, *, gpus: bool) -> Resources:
        return Resources(4, 8 << 30, 2 if gpus else 0, (16 << 30) if gpus else 0)

    def available(self, workdir: PurePosixPath, *, seen: bool | None) -> bool:
        return seen is True

    def placement(self, workdir: PurePosixPath) -> Placement:
        return Placement(self.backend, self.provider, workdir)

    def has(self, tool: str) -> bool | None:
        return self.tools.get(tool)

    # --- what it takes asking

    async def probe(self) -> None:
        self.probed += 1

    async def absolute(self, path: PurePosixPath) -> PurePosixPath:
        if path.parts[:1] == ("~",):
            return self.home.joinpath(*path.parts[1:])
        return path

    async def state(self) -> PurePosixPath:
        return self.where

    async def start(self, argv: Sequence[str], cwd: PurePosixPath) -> ScriptedRun:
        if self.broken is not None:
            raise self.broken
        if cwd not in self.dirs:
            raise EnvUnavailable(f"the workdir {cwd} is not there")
        command = tuple(argv)
        self.started.append((command, cwd))
        run = ScriptedRun(self._scripted(command, cwd))
        self.runs.append(run)
        return run

    def _scripted(self, argv: tuple[str, ...], cwd: PurePosixPath) -> Said:
        """The driver's own scripts, done here; anything else, as `answer` says."""
        if argv[:2] == ("/bin/sh", "-c") and argv[2] == CLONE_SCRIPT:
            source, target = PurePosixPath(argv[4]), PurePosixPath(argv[5])
            if source not in self.dirs:
                return 2, "", f"there is no directory {source} to copy\n"
            self._copy(source, target)
            return 0, "", ""
        if argv[:2] == ("/bin/sh", "-c") and argv[2] == REMOVE_SCRIPT:
            self._gone(PurePosixPath(argv[4]))
            return 0, "", ""
        return self.answer(argv, cwd)

    def _copy(self, source: PurePosixPath, target: PurePosixPath) -> None:
        for one in [one for one in self.dirs if one.is_relative_to(source)]:
            self.dirs.add(target / one.relative_to(source))
        for path, data in list(self.files.items()):
            if path.is_relative_to(source):
                self.files[target / path.relative_to(source)] = data
        self._made(target)

    def _gone(self, top: PurePosixPath) -> None:
        self.dirs = {one for one in self.dirs if not one.is_relative_to(top)}
        self.files = {
            path: data
            for path, data in self.files.items()
            if not path.is_relative_to(top)
        }

    def _made(self, path: PurePosixPath) -> None:
        self.dirs.update((path, *path.parents))

    async def read(self, path: PurePosixPath) -> bytes:
        from hmz.flows import EnvFileNotFound

        try:
            return self.files[path]
        except KeyError:
            raise EnvFileNotFound(f"could not read {path}") from None

    async def write(self, path: PurePosixPath, data: bytes) -> None:
        self._made(path.parent)
        self.files[path] = data

    async def mkdir(self, path: PurePosixPath) -> None:
        if self.broken is not None:
            raise self.broken
        self._made(path)

    async def is_dir(self, path: PurePosixPath) -> bool:
        return path in self.dirs

    async def claim(self, path: PurePosixPath) -> Claim | None:
        if path in self.busy:
            raise TempCloneBusy(f"{path} is held by another process")
        return MemoryClaim(path, self.claims) if self.holds else None

    async def close(self) -> None:
        self.shut += 1


async def until(done: Callable[[], bool]) -> None:
    """Lets the loop run until `done` holds, however many of its turns that takes, bounded."""
    for _ in range(10_000):
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("what was waited for never happened")


def returning(value: object) -> Callable[..., Any]:
    """What answers `value` whatever it is asked, as a stand-in for a function."""

    def given(*_: object, **__: object) -> Any:
        return value

    return given


def same_path(path: str, *, fold_case: bool = False) -> str:
    """A path as the machine would name it, which here is as it is written."""
    return path


def _ok(argv: tuple[str, ...], cwd: PurePosixPath) -> Said:
    return 0, "", ""


# ------------------------------------------------------------------ the far end of a link


#: What a Linux host with two GPUs, git and no bash says to the probe.
PROBE_SAID = (
    "home=/home/me\n"
    "state=/home/me/.hmz\n"
    "cpus=16\n"
    "memkb=1048576\n"
    "gpu=0, GPU-aaaa, 24576\n"
    "gpu=1, GPU-bbbb, 16384\n"
    "git=1\n"
    "bash=0\n"
)


class FakeExec:
    """A command started over a :class:`FakeRemote`."""

    def __init__(self, remote: FakeRemote, ended: Callable[..., None] | None) -> None:
        self.remote = remote
        self.ended = ended
        self.signals: list[int] = []

    def close_stdin(self) -> None:
        return

    def signal(self, number: int) -> None:
        self.signals.append(number)
        ended, self.ended = self.ended, None
        if ended is not None:
            ended({"signal": number}, None)


@dataclass
class FakeRemote:
    """coganchor's serving half at the far end of a link; see the module docstring.

    Attributes:
      probe: What the host says to the probe.
      answer: What answers a command: status, stdout and stderr; an `OSError` it fails
        with; or None to run until it is signalled.
      files: Every file, by absolute path.
      dirs: Every directory, by absolute path.
      commands: Every command started that was not the probe, with where.
      execs: What each of those became, in the same order.
      connects: How many times it was connected to.
      closes: How many times a client of it was closed.
    """

    probe: str = PROBE_SAID
    answer: Callable[[list[str], str], tuple[int, str, str] | OSError | None] = field(
        default=lambda argv, cwd: (0, "", "")
    )
    files: dict[str, bytes] = field(default_factory=dict[str, bytes])
    dirs: set[str] = field(default_factory=lambda: {"/", "/home/me", "/work"})
    commands: list[tuple[list[str], str]] = field(
        default_factory=list[tuple[list[str], str]]
    )
    execs: list[FakeExec] = field(default_factory=list[FakeExec])
    connects: int = 0
    closes: int = 0

    # --- what `RemoteClient` does

    def start(self) -> None:
        return

    def close(self) -> None:
        self.closes += 1

    def start_exec(
        self,
        argv: list[str],
        cwd: str,
        env: Mapping[str, str],
        wrote: Callable[[int, bytes], None],
        ended: Callable[[dict[str, Any] | None, OSError | None], None],
    ) -> FakeExec:
        del env
        if argv == ["/bin/sh", "-c", PROBE_SCRIPT]:
            wrote(1, self.probe.encode())
            ended({"exit_code": 0}, None)
            return FakeExec(self, None)
        self.commands.append((argv, cwd))
        said = self.answer(argv, cwd)
        running = FakeExec(self, ended if said is None else None)
        self.execs.append(running)
        if isinstance(said, OSError):
            ended(None, said)
        elif said is not None:
            status, out, err = said
            if out:
                wrote(1, out.encode())
            if err:
                wrote(2, err.encode())
            ended({"exit_code": status}, None)
        return running

    def call(self, op: object, *, path: str) -> dict[str, Any]:
        del op
        if path in self.dirs:
            return {"kind": "dir"}
        if path in self.files:
            return {"kind": "file"}
        raise OSError(errno.ENOENT, "No such file or directory", path)

    def read_file(self, path: str, sink: io.BytesIO) -> None:
        if path not in self.files:
            raise _remote(errno.ENOENT, path)
        sink.write(self.files[path])

    def write_file(self, path: str, source: io.BytesIO) -> None:
        if path.startswith("/readonly/"):
            raise _remote(errno.EACCES, path)
        self.files[path] = source.read()

    def mkdir(self, path: str, *, parents: bool) -> None:
        del parents
        self.dirs.add(path)


def _remote(number: int, path: str) -> OSError:
    """An error the far end sent back, as coganchor raises one."""
    from hmz.coganchor.proto import RemoteOSError

    return RemoteOSError(number, errno.errorcode[number], path)


class _Link:
    """What `transport.connect` hands back: the `ssh` and the channel over it."""

    def __init__(self) -> None:
        self.channel = object()
        self.process = None
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def reach(
    monkeypatch: pytest.MonkeyPatch,
    remote: FakeRemote | None = None,
    *,
    refused: Exception | None = None,
) -> FakeRemote:
    """Has every connection coganchor's transport makes reach `remote`, or be `refused`.

    Returns:
      The remote, made fresh where none was given.
    """
    from hmz.coganchor import remote as coganchor_remote
    from hmz.coganchor import transport

    far = FakeRemote() if remote is None else remote
    targets: list[str] = []

    def connect(target: object, exported: list[str]) -> _Link:
        del exported
        targets.append(str(target))
        if refused is not None:
            raise refused
        far.connects += 1
        return _Link()

    def client(channel: object) -> FakeRemote:
        del channel
        return far

    monkeypatch.setattr(transport, "connect", connect)
    monkeypatch.setattr(coganchor_remote, "RemoteClient", client)
    return far


# --------------------------------------------------------------------------------- runtimes


@dataclass
class Runtime:
    """A saved runtime of any backend, with every field any of them has."""

    name: str = "box"
    endpoint: str = "local"
    image: str = ""
    cpus: float = 0
    memory: int = 0
    gpus: tuple[str, ...] = ()
    gpu_memory: int = 0
    max_containers: int = 0
    max_tasks: int = 0
    gpu_resource: str = ""
    runtime: str = ""
    run_args: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    nodes: Mapping[str, str] = field(default_factory=dict[str, str])
    ssh_target: str = "ssh://me@box"

    def daemon(self) -> Endpoint:
        from hmz.coganchor.transport import Endpoint

        if self.endpoint == "broken":
            raise ValueError("ssh:nowhere names no stored ssh runtime")
        return Endpoint.parse(self.endpoint)

    def target(self) -> str:
        return self.ssh_target


@dataclass(frozen=True)
class Held:
    """A container a runtime already runs, and what it holds."""

    name: str
    cpus: float | None = None
    memory: int | None = None
    gpus: tuple[str, ...] | str = ()
    labels: Mapping[str, str] = field(
        default_factory=lambda: {"humanize.pid": "42", "humanize.host": "gpubox"}
    )


def runtime(value: Runtime | None) -> Any:
    """A stand-in runtime, typed as whatever a signature asks for."""
    return cast("Any", value)


def held(*containers: Held) -> Any:
    """Stand-in containers, typed as whatever a signature asks for."""
    return cast("Any", list(containers))
