"""A machine reached over ssh, as an environment driver does its work on it.

Over coganchor's own road rather than one of its own: :func:`hmz.coganchor.transport.connect`
ships coganchor's serving half to the host -- a zipapp, cached there by its digest, run by
whatever Python 3.12 or newer the host has -- and starts it with `ssh`, and a
:class:`~hmz.coganchor.remote.RemoteClient` speaks to it. That half runs each command in a
process group of its own and sends its stdout and stderr apart, kills the group when asked,
and reads and writes files -- a write atomically, making the directories above it -- which
is everything a driver needs, so nothing is added to the wire. Every `ssh` it starts rides
one master connection per host (`ControlMaster`), and the serving half is started once per
root driver and shared by everything derived from it.

Exported whole, `/` to `/`: the paths a driver names are the host's own, and a flow may read
any file the user there may.

Nothing here touches the network until something is asked of the machine; :meth:`probe`
connects, asks where home is and what the host has -- CPUs, memory, GPUs by `nvidia-smi` --
in one command, and those answers are kept.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import io
import posixpath
import re
import shlex
import signal
import threading
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from hmz.flows import EnvBackendKind, EnvConnectionError, EnvError, EnvUnavailable

from .environing import (
    GPU_QUERY,
    KILLED_WITHIN,
    Machine,
    Resources,
    env_error,
    gpus_of,
    started_error,
)
from .spi import Placement

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence

    from hmz.coganchor.proto import Stream
    from hmz.coganchor.remote import ExecHandle, RemoteClient
    from hmz.coganchor.transport import Transport

__all__ = ["PROBE_SCRIPT", "SSHMachine", "facts_of"]

#: What an ssh destination may be: `host`, `user@host`, either with `:port`, or an alias of
#: the user's ssh config. Never beginning with `-`, which `ssh` would read as an option.
_PROVIDER = re.compile(
    r"(?:[A-Za-z0-9_][A-Za-z0-9._%+-]*@)?[A-Za-z0-9_][A-Za-z0-9._-]*(?::[0-9]{1,5})?"
)

#: What `ssh` says of a host name nothing resolves, which is a host that is not there rather
#: than one that could not be reached.
_NO_SUCH_HOST = ("Could not resolve hostname", "Name or service not known")

#: How long the one command that learns what a host has may take.
_PROBE_WITHIN = 60.0

#: What a host is asked when it is first reached, in POSIX sh, as `key=value` lines: its home,
#: humanize's home there, its CPUs, memory and GPUs, and `CUDA_VISIBLE_DEVICES` if it is set.
PROBE_SCRIPT = rf"""
printf 'home=%s\n' "$HOME"
printf 'state=%s\n' "${{HUMANIZE_HOME:-$HOME/.humanize}}"
printf 'cpus=%s\n' "$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null \
  || sysctl -n hw.ncpu 2>/dev/null)"
if [ -r /proc/meminfo ]; then
  printf 'memkb=%s\n' "$(sed -n 's/^MemTotal: *\([0-9]*\) kB$/\1/p' /proc/meminfo)"
else
  printf 'memory=%s\n' "$(sysctl -n hw.memsize 2>/dev/null)"
fi
[ -z "${{CUDA_VISIBLE_DEVICES+set}}" ] || printf 'cuda=%s\n' "$CUDA_VISIBLE_DEVICES"
if command -v nvidia-smi >/dev/null 2>&1; then
  {shlex.join(GPU_QUERY)} 2>/dev/null | sed 's/^/gpu=/'
fi
exit 0
"""


@dataclass(frozen=True, slots=True)
class _Facts:
    """What a host said about itself when it was reached."""

    home: PurePosixPath
    state: PurePosixPath
    resources: Resources


def facts_of(said: str) -> _Facts:
    """What :data:`PROBE_SCRIPT` printed, read.

    Raises:
      EnvConnectionError: If it did not say where home is.
    """
    values: dict[str, str] = {}
    gpus: list[str] = []
    for line in said.splitlines():
        key, _, value = line.partition("=")
        if key == "gpu":
            gpus.append(value)
        else:
            values.setdefault(key, value.strip())
    home = values.get("home", "")
    if not home.startswith("/"):
        raise EnvConnectionError(f"the host did not say where its home is: {said!r}")
    state = PurePosixPath(home) / PurePosixPath(values.get("state") or ".humanize")
    cpus = int(values["cpus"]) if values.get("cpus", "").isdigit() else 1
    if values.get("memkb", "").isdigit():
        memory = int(values["memkb"]) * 1024
    else:
        memory = int(values["memory"]) if values.get("memory", "").isdigit() else 0
    count, least = gpus_of(gpus, values.get("cuda"))
    return _Facts(
        PurePosixPath(home),
        PurePosixPath(posixpath.normpath(str(state))),
        Resources(max(cpus, 1), memory, count, least),
    )


# ---------------------------------------------------------------------- the connection


def _ran_now(client: RemoteClient, argv: list[str], cwd: str, within: float) -> str:
    """Runs a short command over a client, from a thread that may wait, for its stdout.

    Raises:
      OSError: If it could not be run, did not succeed, or took longer than `within`.
    """
    out: list[bytes] = []
    err: list[bytes] = []
    done = threading.Event()
    ended: list[tuple[dict[str, Any] | None, OSError | None]] = []

    def wrote(stream: Stream, data: bytes) -> None:
        (err if int(stream) == 2 else out).append(data)  # noqa: PLR2004 -- stderr

    def finished(payload: dict[str, Any] | None, why: OSError | None) -> None:
        ended.append((payload, why))
        done.set()

    handle = client.start_exec(argv, cwd, {}, wrote, finished)
    with contextlib.suppress(OSError):
        handle.close_stdin()
    if not done.wait(within):
        handle.signal(signal.SIGKILL)
        raise TimeoutError(errno.ETIMEDOUT, f"{argv[0]} took longer than {within:g}s")
    payload, why = ended[0]
    if why is not None:
        raise why
    if (payload or {}).get("exit_code") != 0:
        said = b"".join(err).decode("utf-8", "replace").strip()
        raise OSError(errno.EIO, f"{argv[0]} failed: {said or payload}")
    return b"".join(out).decode("utf-8", "replace")


def _opened(provider: str) -> tuple[Transport, RemoteClient, _Facts]:
    """Reaches a host and learns what it has, from a thread that may wait.

    Raises:
      EnvUnavailable: If there is no such host.
      EnvConnectionError: If it could not be reached, or would not serve.
    """
    from hmz.coganchor import transport
    from hmz.coganchor.proto import ProtocolError
    from hmz.coganchor.remote import RemoteClient

    try:
        link = transport.connect(transport.Target.parse(f"ssh://{provider}"), ["/"])
    except ValueError as error:
        raise EnvUnavailable(f"{provider!r} is not an ssh host: {error}") from error
    except OSError as error:
        said = str(error)
        if any(clue in said for clue in _NO_SUCH_HOST):
            raise EnvUnavailable(f"there is no ssh host {provider}: {said}") from error
        raise EnvConnectionError(
            f"could not reach {provider} over ssh: {said}"
        ) from error
    client = RemoteClient(link.channel)
    try:
        client.start()
        facts = facts_of(
            _ran_now(client, ["/bin/sh", "-c", PROBE_SCRIPT], "/", _PROBE_WITHIN)
        )
    except BaseException as error:
        _shut(link, client)
        if isinstance(error, (OSError, ProtocolError)):
            raise EnvConnectionError(
                f"could not reach {provider} over ssh: {error}"
            ) from error
        raise
    return link, client, facts


def _shut(link: Transport | None, client: RemoteClient | None) -> None:
    """Lets go of a connection, from a thread that may wait: the client, then `ssh`."""
    try:
        if client is not None:
            client.close()
    finally:
        if link is not None:
            link.close()


def _is_dir_now(client: RemoteClient, path: str) -> bool:
    """Whether a directory is at a path on the host, following links, from a thread."""
    from hmz.coganchor.proto import Op

    for _ in range(40):
        try:
            said = client.call(Op.STAT, path=path)
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ENOTDIR):
                return False
            raise
        if said.get("kind") != "link":
            return said.get("kind") == "dir"
        target = str(said.get("target") or "")
        path = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
    return False


# ------------------------------------------------------------------------------ commands


class _RemoteRun:
    """One command running on the host, heard back on the client's reader thread."""

    __slots__ = (
        "_argv",
        "_cwd",
        "_done",
        "_err",
        "_gave_up",
        "_killing",
        "_loop",
        "_machine",
        "_out",
        "_released",
        "handle",
    )

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        machine: SSHMachine,
        argv: Sequence[str],
        cwd: str,
    ) -> None:
        self._loop = loop
        self._machine = machine
        self._argv = argv
        self._cwd = cwd
        self._out: list[bytes] = []
        self._err: list[bytes] = []
        self._done: asyncio.Future[int] = loop.create_future()
        #: Set once it was killed and waited for, whether or not the host said it ended.
        self._gave_up: asyncio.Future[None] = loop.create_future()
        #: The one killing of it, however many ask for it.
        self._killing: asyncio.Task[None] | None = None
        self._released = False
        self.handle: ExecHandle | None = None

    def start_now(self, client: RemoteClient) -> None:
        """Starts it, with nothing on its stdin, from a thread that may wait to send."""
        self.handle = client.start_exec(
            list(self._argv), self._cwd, {}, self.wrote, self.ended
        )
        with contextlib.suppress(OSError):
            self.handle.close_stdin()

    def wrote(self, stream: Stream, data: bytes) -> None:
        """Keeps what it wrote. On the reader thread, before :meth:`ended` for it."""
        (self._err if int(stream) == 2 else self._out).append(data)  # noqa: PLR2004

    def ended(self, payload: dict[str, Any] | None, why: OSError | None) -> None:
        """Hands how it ended to the loop. On the reader thread."""
        with contextlib.suppress(RuntimeError):  # the loop is gone, and nobody waits
            self._loop.call_soon_threadsafe(self._settle, payload, why)

    def _settle(self, payload: dict[str, Any] | None, why: OSError | None) -> None:
        if self._done.done():
            return
        if why is not None:
            self._done.set_exception(why)
            if self._released:
                # Read here, since nobody waits on one that was let go of, and a failure
                # nobody read is reported as one nobody heard about.
                self._done.exception()
            return
        said = payload or {}
        if said.get("exit_code") is not None:
            self._done.set_result(int(said["exit_code"]))
        else:
            # Killed by a signal, as a shell reports it; one that ended without saying how
            # did not succeed.
            killed = int(said.get("signal") or 0)
            self._done.set_result(128 + killed if killed else 1)

    async def finished(self) -> tuple[int, bytes, bytes]:
        # Neither future is cancelled by a cancelled wait: `kill` goes on waiting on one,
        # and sets the other.
        await asyncio.wait(
            {self._done, self._gave_up}, return_when=asyncio.FIRST_COMPLETED
        )
        if not self._done.done():
            raise EnvError(
                f"{self._argv[0]!r} was killed on {self._machine.provider}, and was not "
                f"heard to end within {KILLED_WITHIN:g}s"
            )
        why = self._done.exception()
        if isinstance(why, OSError):
            # One of the client's own is the connection gone; one the host sent is about
            # the command, over a connection that works.
            reported = isinstance(why, _reported())
            if not reported and isinstance(why, ConnectionError):
                self._machine.lost()
            raise started_error(why, self._argv, self._cwd, reported=reported) from why
        return self._done.result(), b"".join(self._out), b"".join(self._err)

    async def kill(self) -> None:
        # Once, and waited on by everyone who asks -- and not cancelled with any of them.
        if self._killing is None:
            self._killing = asyncio.ensure_future(self._kill())
        await asyncio.shield(self._killing)

    async def _kill(self) -> None:
        handle = self.handle
        if handle is not None and not self._done.done():
            # Not waited for past the wait below: asking waits on the client's own timeout,
            # which a link that has stalled takes minutes to reach.
            _background(asyncio.to_thread(handle.signal, signal.SIGKILL))
        await asyncio.wait({self._done}, timeout=KILLED_WITHIN)
        if not self._gave_up.done():
            self._gave_up.set_result(None)

    def release(self) -> None:
        # What it ended with is read here if nobody else did, so that a command given up on
        # is not reported later as a failure nobody heard about.
        self._released = True
        if self._done.done() and not self._done.cancelled():
            self._done.exception()


#: What is being done in the background because nobody is left to wait on it.
_BACKGROUND: set[asyncio.Future[Any]] = set()


def _background(doing: Coroutine[Any, Any, Any]) -> None:
    """Lets something run to its end without anybody waiting on it, or it being lost."""
    task = asyncio.ensure_future(doing)
    _BACKGROUND.add(task)

    def over(done: asyncio.Future[Any]) -> None:
        _BACKGROUND.discard(done)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(over)


def _abandoned(running: _RemoteRun, starting: asyncio.Future[None]) -> None:
    """Kills a command whose starter was cancelled, once it has started, if it did."""
    if starting.cancelled() or starting.exception() is not None:
        return
    _background(running.kill())


def _reported() -> type[OSError]:
    """What an error the host sent is raised as."""
    from hmz.coganchor.proto import RemoteOSError

    return RemoteOSError


# -------------------------------------------------------------------------------- machine


class SSHMachine(Machine):
    """A host reached over ssh, connected to the first time something is asked of it."""

    backend = EnvBackendKind.SSH

    def __init__(self, provider: str) -> None:
        """Initializes a machine that has not been reached.

        Args:
          provider: The ssh destination: `[user@]host[:port]`, or an alias of ssh's config.

        Raises:
          EnvUnavailable: If that is not an ssh destination.
        """
        super().__init__()
        if not _PROVIDER.fullmatch(provider):
            raise EnvUnavailable(
                f"{provider!r} is not an ssh host, as [user@]host[:port]"
            )
        self.provider = provider
        self.identity = f"ssh:{provider}"
        self._link: Transport | None = None
        self._client: RemoteClient | None = None
        self._facts: _Facts | None = None
        self._opening: asyncio.Task[tuple[RemoteClient, _Facts]] | None = None
        self._generation = 0
        self._reached = False
        self._broken = False

    # --- the connection

    def lost(self) -> None:
        """Marks the connection broken, so that the next ask connects again."""
        self._broken = True

    def _live(self) -> RemoteClient | None:
        """The client, while its connection holds."""
        client, link = self._client, self._link
        if client is None or link is None or self._broken:
            return None
        if link.process is not None and link.process.poll() is not None:
            return None
        return client

    async def _connected(self) -> tuple[RemoteClient, _Facts]:
        """A client that is connected, and what the host said, connecting where need be.

        One connection is made however many ask at once; a caller cancelled while it is
        being made leaves it to be made for the next.
        """
        client, facts = self._live(), self._facts
        if client is not None and facts is not None:
            return client, facts
        if self.closed:
            raise EnvConnectionError(f"the connection to {self.provider} was closed")
        opening = self._opening
        if opening is None:
            opening = asyncio.ensure_future(self._open(self._generation))
            self._opening = opening

            def landed(task: asyncio.Task[tuple[RemoteClient, _Facts]]) -> None:
                if self._opening is task:
                    self._opening = None
                if not task.cancelled():
                    task.exception()

            opening.add_done_callback(landed)
        return await asyncio.shield(opening)

    async def _open(self, generation: int) -> tuple[RemoteClient, _Facts]:
        stale = (self._link, self._client)
        self._link = self._client = None
        if stale != (None, None):
            await asyncio.to_thread(_shut, *stale)
        try:
            link, client, facts = await asyncio.to_thread(_opened, self.provider)
        except EnvError:
            self._reached = False
            raise
        if generation != self._generation:
            await asyncio.to_thread(_shut, link, client)
            raise EnvConnectionError(f"the connection to {self.provider} was closed")
        self._link, self._client, self._facts = link, client, facts
        self._reached, self._broken = True, False
        return client, facts

    def _failed(self, error: OSError, doing: str, *, missing: bool = False) -> EnvError:
        """The environment error one ask over the connection came to.

        One the host sent back is about what was asked, whatever its errno says -- a stale
        network mount there answers ENOTCONN over a connection that works -- and so is one
        ask that went unanswered for the client's whole timeout, which a hung mount there
        does too. Only the client finding the connection gone marks it broken, since
        connecting again kills everything running on it.
        """
        reported = isinstance(error, (_reported(), TimeoutError))
        failed = env_error(
            error, f"{doing} on {self.provider}", missing=missing, reported=reported
        )
        if isinstance(failed, EnvConnectionError):
            self.lost()
        return failed

    async def close(self) -> None:
        self._generation += 1
        link, client = self._link, self._client
        self._link = self._client = None
        if link is not None or client is not None:
            await asyncio.to_thread(_shut, link, client)

    # --- what is known without asking

    def resources(self, *, gpus: bool) -> Resources:
        """What the host said it has, or the least anything has before it was reached."""
        del gpus
        facts = self._facts
        return facts.resources if facts is not None else Resources()

    def available(self, workdir: PurePosixPath, *, seen: bool | None) -> bool:
        """Whether the host answered, the connection holds, and the workdir was there."""
        del workdir
        return self._reached and not self._broken and seen is True

    def placement(self, workdir: PurePosixPath) -> Placement:
        """An anchored machine at the host, whose workspace is the workdir there.

        A `~/...` workdir is named by its absolute path once the host has said where home
        is, and before that as the target's own path for this machine's workspace.
        """
        from hmz.coganchor import AnchorConfig
        from hmz.coganchor.machines import AnchoredConfig

        target = f"ssh://{self.provider}"
        facts = self._facts
        if workdir.is_absolute():
            anchor = AnchorConfig(target=target, workspace=str(workdir))
        elif facts is not None:
            anchor = AnchorConfig(target=target, workspace=str(_homed(facts, workdir)))
        else:
            anchor = AnchorConfig(target=target, remote_path=str(workdir))
        return Placement(
            EnvBackendKind.SSH, self.provider, workdir, AnchoredConfig(anchor=anchor)
        )

    # --- what it takes asking

    async def probe(self) -> None:
        await self._connected()

    async def absolute(self, path: PurePosixPath) -> PurePosixPath:
        if path.parts[:1] != ("~",):
            return path
        _, facts = await self._connected()
        return _homed(facts, path)

    async def state(self) -> PurePosixPath:
        _, facts = await self._connected()
        return facts.state

    async def start(self, argv: Sequence[str], cwd: PurePosixPath) -> _RemoteRun:
        client, _ = await self._connected()
        running = _RemoteRun(asyncio.get_running_loop(), self, argv, str(cwd))
        # On a thread, since sending waits its turn behind whatever else is being sent -- a
        # file being written is 64 KiB at a time -- and the loop waits for nothing.
        starting = asyncio.ensure_future(asyncio.to_thread(running.start_now, client))
        try:
            await asyncio.shield(starting)
        except asyncio.CancelledError:
            starting.add_done_callback(lambda _: _abandoned(running, starting))
            raise
        except OSError as error:
            raise self._failed(error, f"could not run {argv[0]!r}") from error
        return running

    async def read(self, path: PurePosixPath) -> bytes:
        client, _ = await self._connected()
        sink = io.BytesIO()
        try:
            await asyncio.to_thread(client.read_file, str(path), sink)
        except OSError as error:
            raise self._failed(error, f"could not read {path}", missing=True) from error
        return sink.getvalue()

    async def write(self, path: PurePosixPath, data: bytes) -> None:
        client, _ = await self._connected()
        try:
            await asyncio.to_thread(client.write_file, str(path), io.BytesIO(data))
        except OSError as error:
            raise self._failed(error, f"could not write {path}") from error

    async def mkdir(self, path: PurePosixPath) -> None:
        client, _ = await self._connected()
        try:
            await asyncio.to_thread(client.mkdir, str(path), parents=True)
        except OSError as error:
            raise self._failed(error, f"could not make the directory {path}") from error

    async def is_dir(self, path: PurePosixPath) -> bool:
        client, _ = await self._connected()
        try:
            return await asyncio.to_thread(_is_dir_now, client, str(path))
        except OSError as error:
            raise self._failed(error, f"could not look at {path}") from error


def _homed(facts: _Facts, path: PurePosixPath) -> PurePosixPath:
    """A `~/...` path under the home the host said it has."""
    return facts.home.joinpath(*path.parts[1:])
