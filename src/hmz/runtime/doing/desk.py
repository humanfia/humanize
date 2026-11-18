"""What a frontend can do in each environment a run holds: its files, a shell, its git.

A host lists every environment its run holds -- each role's, the run's own workspace, and
each one a flow derived -- and serves the `env.*` requests against them: through the real
driver, which is to say by what the environment can do rather than what its role declared,
on the run's own loop, since that is where a driver lives.

The driver methods the panels need beyond what a flow is given -- listing a directory, a
terminal -- are asked of it by shape (:class:`Browsable`, :class:`Terminable`): a driver
without them is an environment without files, or without a shell, and is refused as one.

A terminal is shared: whoever opened it and whoever reattached to it each see its output,
told only to them, in chunks of at most :data:`CHUNK` sent every :data:`COALESCE` seconds.
Each holds at most :data:`CREDIT` bytes it has not acknowledged; past that nothing more is
sent to it, and while no viewer has room the terminal is not read at all, so a program
printing faster than anybody reads it is held up by its own pty rather than filling the
host. One with no viewers is read on into its scrollback (the last :data:`SCROLLBACK` bytes),
which a viewer reattaching is handed first; it is killed after :data:`IDLE` seconds with
nobody watching, and as its environment closes.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import collections
import concurrent.futures
import contextlib
import dataclasses
import functools
import hashlib
import itertools
import json
import posixpath
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from hmz.flows import (
    BashEnvMixin,
    FilesEnvMixin,
    GitEnvMixin,
    GitWorktreeEnvMixin,
    RewindableEnvMixin,
    ScratchDirEnvMixin,
    ShellEnvMixin,
    TemporaryClonedDirEnvMixin,
)

from . import gitdesk

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence
    from pathlib import PurePosixPath

__all__ = [
    "CAPS",
    "CHUNK",
    "COALESCE",
    "CREDIT",
    "IDLE",
    "READ_MAX",
    "SCROLLBACK",
    "Browsable",
    "Desk",
    "Held",
    "Holds",
    "Homed",
    "Pty",
    "Refused",
    "Terminable",
    "caps_of",
]

#: Each environment mixin a driver may serve, by the name a frontend knows it by, in the
#: order they are listed.
CAPS: dict[str, type] = {
    "files": FilesEnvMixin,
    "shell": ShellEnvMixin,
    "bash": BashEnvMixin,
    "git": GitEnvMixin,
    "git_worktree": GitWorktreeEnvMixin,
    "rewind": RewindableEnvMixin,
    "scratch": ScratchDirEnvMixin,
    "temp_clone": TemporaryClonedDirEnvMixin,
}

#: The most of a file one `env.read` answers, in bytes.
READ_MAX = 1 << 20

#: The most of a terminal's output one message carries, in bytes.
CHUNK = 64 << 10

#: How long a terminal's output is gathered before it is sent, in seconds.
COALESCE = 0.016

#: How much of a terminal's output a viewer may have unacknowledged before none is sent.
CREDIT = 1 << 20

#: How much of a terminal's output is kept for a viewer reattaching, in bytes.
SCROLLBACK = 256 << 10

#: How long a terminal nobody watches lives on, in seconds.
IDLE = 600.0

#: How much of what a viewer has not been sent yet is kept for it, the newest kept: a viewer
#: falls this far behind only while another, with room, keeps the terminal being read.
_BEHIND = CREDIT

#: How long one operation on a driver may take before it is given up on, in seconds.
_PATIENCE = 120.0

#: How much of the files read is kept, by bytes, for reading the same one again in chunks.
_CACHED = 128 << 20

#: How many links are followed from a path to the file it is read as, as many as Linux follows.
_HOPS = 40

#: Says a chunk of a file too large to hold: its SHA-256 first where asked for, then `.`,
#: then the chunk in base64. Arguments: the path, the offset, the length, and `1` for the hash.
_RANGE = (
    'f=$1; off=$2; len=$3; if [ "$4" = 1 ]; then '
    '{ sha256sum < "$f" 2>/dev/null || shasum -a 256 < "$f"; } | cut -c1-64; fi; '
    'echo .; tail -c +"$((off + 1))" "$f" | head -c "$len" | base64'
)

#: The most `env.find` and `env.search` answer.
_FIND_MOST = 100_000
_SEARCH_MOST = 10_000

#: How much `find` may print before the listing is cut short, in bytes.
_LISTED = 32 << 20

#: The longest a line found by `env.search` is said, in characters.
_LINE = 1000

#: Which exit status a terminal whose environment closed under it is said to have ended
#: with: hung up on.
_HUNG_UP = 129

_CLOSED = "That environment has closed."

#: Lists every file under the workdir for quick-open: what git tracks and does not ignore
#: inside a repository, and otherwise everything but `.git` and `node_modules`.
_FIND = (
    "if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then "
    "GIT_OPTIONAL_LOCKS=0 git --no-optional-locks -c core.quotepath=off "
    "ls-files -z -co --exclude-standard; "
    "else find . \\( -name .git -o -name node_modules \\) -prune -o \\( -type f -o -type l \\) "
    "-print0; fi | head -c $1"
)

#: Searches the files `_FIND` lists: with `rg --json` where there is `rg`, which is told to
#: search hidden files too and to heed no `.ignore` file, which git knows nothing of, and
#: outside a repository to heed no ignore file at all and to leave `node_modules` out; else
#: with `git grep` inside a repository; else with `grep`, which where it knows no long option,
#: as BusyBox's does not, is given the files `find` lists that hold no NUL byte.
#: Arguments: the query, `F` or `E`, `i` or `s`, the glob, and how many lines to print.
_SEARCH = (
    "q=$1; how=$2; case_=$3; glob=$4; most=$5; set --; "
    "if command -v rg >/dev/null 2>&1; then echo rg; "
    "set -- --json --max-columns 1000 --max-columns-preview; "
    '[ "$how" = F ] && set -- "$@" --fixed-strings; '
    '[ "$case_" = i ] && set -- "$@" --ignore-case || set -- "$@" --case-sensitive; '
    '[ -n "$glob" ] && set -- "$@" --glob "$glob"; '
    "set -- \"$@\" --hidden --no-ignore-dot --glob '!.git'; "
    "git rev-parse --is-inside-work-tree >/dev/null 2>&1 || "
    "set -- \"$@\" --no-ignore --glob '!node_modules'; "
    'rg "$@" -e "$q" -- . 2>/dev/null | head -n "$most"; '
    "elif git rev-parse --is-inside-work-tree >/dev/null 2>&1; then echo grep; "
    'set -- -nI --no-color --untracked --exclude-standard "-$how"; '
    '[ "$case_" = i ] && set -- "$@" -i; '
    'set -- "$@" -e "$q" --; [ -n "$glob" ] && set -- "$@" "$glob"; '
    "GIT_OPTIONAL_LOCKS=0 GIT_PAGER=cat git --no-optional-locks -c core.quotepath=off "
    'grep "$@" 2>/dev/null | head -n "$most"; '
    "else echo grep; "
    "if grep --include=x --exclude-dir=x -q x /dev/null 2>/dev/null; "
    '[ "$?" -lt 2 ]; then '
    'set -- -rnI --exclude-dir=.git --exclude-dir=node_modules "-$how"; '
    '[ "$case_" = i ] && set -- "$@" -i; '
    '[ -n "$glob" ] && set -- "$@" "--include=$glob"; '
    'grep "$@" -e "$q" -- . 2>/dev/null | head -n "$most"; '
    'else [ "$case_" = i ] && how=${how}i; '
    "how=$how q=$q find . \\( -name .git -o -name node_modules \\) -prune -o "
    '-type f -name "${glob:-*}" -exec sh -c \''
    'for f do tr -d "\\000" <"$f" | cmp -s - "$f" && set -- "$@" "$f"; shift; done; '
    '[ "$#" -eq 0 ] || grep "-Hn$how" -e "$q" -- "$@"\' sh {} + '
    '2>/dev/null | head -n "$most"; fi; fi'
)


class Refused(Exception):  # noqa: N818 -- named for what happened, as the runner's is
    """A request about an environment that cannot be done, in the words a frontend is told."""


# ------------------------------------------------------------------------ what is asked


class Entry(Protocol):
    """One entry of a directory, as a driver lists it."""

    @property
    def name(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def size(self) -> int: ...
    @property
    def mtime(self) -> float: ...
    @property
    def target(self) -> str | None: ...


@runtime_checkable
class Browsable(Protocol):
    """A driver whose files can be browsed and changed beyond reading and writing one."""

    async def list(self, path: str) -> Sequence[Entry]:
        """The entries of a directory."""
        ...

    async def stat(self, path: str) -> Entry:
        """One file's entry, the link itself for a link."""
        ...

    async def mkdir(self, path: str) -> None:
        """Makes a directory and those above it."""
        ...

    async def rename(self, path: str, to: str) -> None:
        """Moves a file or a directory."""
        ...

    async def remove(self, path: str) -> None:
        """Removes a file, or a directory and everything in it."""
        ...


@runtime_checkable
class Homed(Protocol):
    """A driver whose paths may be under a home, `~/...`, that only its machine knows."""

    async def absolute(self, path: str) -> str:
        """A path as an absolute one, a leading `~` resolved to the home there."""
        ...


class Pty(Protocol):
    """A program running on a terminal of its own."""

    async def read(self) -> bytes:
        """What it printed next, b"" once it is over."""
        ...

    async def write(self, data: bytes) -> None:
        """Types into it."""
        ...

    async def resize(self, cols: int, rows: int) -> None:
        """Tells it its terminal is a new size."""
        ...

    async def wait(self) -> int:
        """Its exit status, 128 and the signal for a signal."""
        ...

    async def kill(self) -> None:
        """Kills it and everything it started. Never raises."""
        ...


@runtime_checkable
class Terminable(Protocol):
    """A driver that can run a program on a terminal."""

    async def pty(self, argv: Sequence[str] | None, *, cols: int, rows: int) -> Pty:
        """Starts one: `argv`, or a login shell for None."""
        ...


class Held(Protocol):
    """One environment a run holds, as its engine lists it."""

    @property
    def role(self) -> str: ...
    @property
    def chain(self) -> str: ...
    @property
    def parent(self) -> str | None: ...
    @property
    def driver(self) -> Any: ...
    @property
    def declared(self) -> frozenset[type]: ...


class Holds(Protocol):
    """A run going, as far as its environments go: what it holds, and the loop they live on."""

    @property
    def loop(self) -> asyncio.AbstractEventLoop: ...

    def held_envs(self) -> Sequence[Held]:
        """Every environment it holds, oldest first. From any thread."""
        ...


def caps_of(capabilities: frozenset[type]) -> list[str]:
    """The names of the environment mixins `capabilities` serve, in :data:`CAPS` order.

    A mixin is served by itself and by any mixin implementing it, which is how
    `RewindableEnvMixin`, an interface no driver lists, is served: by `GitEnvMixin`.
    """
    return [
        name
        for name, mixin in CAPS.items()
        if any(mixin in one.__mro__ for one in capabilities)
    ]


# ------------------------------------------------------------------------- what is held


@dataclasses.dataclass(slots=True, eq=False)
class _Env:
    """One environment listed, and what is kept about it."""

    id: str
    run: int
    role: str
    chain: str
    parent: str | None
    driver: Any
    loop: asyncio.AbstractEventLoop
    caps: list[str]
    declared: list[str]
    facts: dict[str, int | None]
    open: bool = True
    top: str | None = None

    def described(self) -> dict[str, Any]:
        driver = self.driver
        try:
            available = bool(driver.available)
        except Exception:  # noqa: BLE001 -- a machine nobody can look at is not available
            available = False
        return {
            "id": self.id,
            "role": self.role,
            "chain": self.chain,
            "parent": self.parent,
            "run": self.run,
            "backend": str(driver.backend),
            "provider": str(driver.provider),
            "workdir": str(driver.workdir),
            "available": available and self.open,
            "open": self.open,
            "caps": list(self.caps),
            "declared": list(self.declared),
            "facts": dict(self.facts),
        }


def _facts(driver: Any) -> dict[str, int | None]:
    facts: dict[str, int | None] = {}
    for name, attribute in (
        ("cpu", "cpu_count"),
        ("memory", "memory"),
        ("gpu_count", "gpu_count"),
        ("gpu_memory", "gpu_memory"),
    ):
        try:
            facts[name] = int(getattr(driver, attribute))
        except Exception:  # noqa: BLE001 -- a fact nobody could read is not found
            facts[name] = None
    return facts


@dataclasses.dataclass(slots=True, eq=False)
class _Viewer:
    """One frontend watching a terminal: what it has not been sent, and not acknowledged."""

    pending: bytearray = dataclasses.field(default_factory=bytearray)
    unacked: int = 0


@dataclasses.dataclass(slots=True, eq=False)
class _Term:
    """One terminal, and who watches it."""

    id: str
    env: _Env
    cols: int
    rows: int
    pty: Pty
    room: asyncio.Event
    viewers: dict[str, _Viewer] = dataclasses.field(default_factory=dict[str, _Viewer])
    scroll: bytearray = dataclasses.field(default_factory=bytearray)
    alive: bool = True
    status: int | None = None
    told_exit: bool = False
    flushing: bool = False
    roomy: bool = True
    alone_since: float = dataclasses.field(default_factory=time.monotonic)

    #: What it runs, as `shell` answers it: None for the login shell.
    shell: list[str] | None = None
    title: str = "shell"


# ---------------------------------------------------------------------------- the desk


class Desk:
    """Every environment one host's run holds, and what its frontends do in them.

    Thread-safe. Nothing here takes the host's lock while holding its own: the host's
    `record` and `guard` are called outside it, and `post` takes only a frontend's outbox.
    """

    def __init__(
        self,
        *,
        post: Callable[[str, dict[str, Any]], object],
        record: Callable[[dict[str, Any]], None],
        guard: Callable[[int, Any], str | None],
    ) -> None:
        """A desk listing nothing yet.

        Args:
          post: Says a message to one frontend, by its client id: what a terminal printed.
          record: Writes a record into the run's history, for every frontend.
          guard: The role of a session with a turn open in an environment -- by its run and
            driver -- or None for none; a rewind is refused while there is one.
        """
        self._post = post
        self._record = record
        self._guard = guard
        self._lock = threading.Lock()
        self._envs: dict[str, _Env] = {}
        self._terms: dict[str, _Term] = {}
        self._counted = itertools.count(1)
        self._cache: collections.OrderedDict[
            tuple[str, str, float, int], tuple[bytes, str]
        ] = collections.OrderedDict()
        self._cached = 0
        #: The etag of each file too large to hold, by where it is and how it stands.
        self._etags: dict[tuple[str, str, float, int], str] = {}
        #: Held while the catalog is looked over, which two threads may ask for at once.
        self._refreshing = threading.Lock()
        git_paths = functools.partial(self._git_paths)
        self._doing: dict[str, Callable[[str, str, dict[str, Any]], dict[str, Any]]] = {
            "env.list": self._list,
            "env.stat": self._stat,
            "env.read": self._read,
            "env.find": self._find,
            "env.search": self._search,
            "env.write": self._write,
            "env.mkdir": self._mkdir,
            "env.rename": self._rename,
            "env.remove": self._remove,
            "env.term.open": self._term_open,
            "env.term.input": self._term_input,
            "env.term.resize": self._term_resize,
            "env.term.ack": self._term_ack,
            "env.term.close": self._term_close,
            "env.term.list": self._term_list,
            "env.git.status": self._git_status,
            "env.git.diff": self._git_diff,
            "env.git.log": self._git_log,
            "env.git.stage": git_paths(gitdesk.stage, "staged"),
            "env.git.unstage": git_paths(gitdesk.unstage, "unstaged"),
            "env.git.discard": git_paths(gitdesk.discard, "discarded"),
            "env.git.commit": self._git_commit,
            "env.git.snapshots": self._git_snapshots,
            "env.git.rewind": self._git_rewind,
        }

    # ------------------------------------------------------------------ the catalog

    def refresh(
        self, run: int, holds: Holds | None, *, going: bool
    ) -> list[dict[str, Any]]:
        """Lists the environments a run holds now, and closes those it no longer does.

        Args:
          run: Which run of the host it is.
          holds: What it holds, or None before it has started holding anything.
          going: Whether the run is still running or stopping; once it is not, every
            environment of it is closed.

        Returns:
          Every environment listed, as the `envs` snapshot says it.
        """
        with self._refreshing:
            listed = self._refreshed(run, holds, going=going)
        return [one.described() for one in listed]

    def _refreshed(self, run: int, holds: Holds | None, *, going: bool) -> list[_Env]:
        held: Sequence[Held] = ()
        loop: asyncio.AbstractEventLoop | None = None
        if holds is not None and going:
            with contextlib.suppress(Exception):
                loop = holds.loop
                held = holds.held_envs()
        with self._lock:
            before = dict(self._envs)
            if going and loop is None:
                # Not holding anything yet, or past holding it and not yet over: as it was.
                return [one for one in before.values() if one.run == run]
        fresh: dict[str, _Env] = {}
        # An environment is one driver: two may share a chain, as two worktrees of one ref do.
        known = {
            id(was.driver): was
            for was in before.values()
            if was.open and was.run == run
        }
        keys = {known[id(one.driver)].id for one in held if id(one.driver) in known}
        chains: dict[str, str] = {}
        roots = {one.chain: one for one in held}
        for one in held:
            if loop is None:
                continue
            # Its label is its role and what derived it; where its root is, is its id's.
            root = one
            while root.parent in roots:
                root = roots[root.parent]
            label = one.role + one.chain[len(root.chain) :]
            was = known.get(id(one.driver))
            if was is not None:
                # The workspace is named by the role that takes it once one does.
                was.role = one.role
                was.chain = label
                was.declared = caps_of(frozenset(one.declared))
                fresh[was.id] = was
                chains.setdefault(one.chain, was.id)
                continue
            key = f"{run}:{one.chain}"
            for n in itertools.count(2):
                if key not in keys:
                    break
                key = f"{run}:{one.chain}~{n}"
            keys.add(key)
            chains.setdefault(one.chain, key)
            fresh[key] = _Env(
                id=key,
                run=run,
                role=one.role,
                chain=label,
                parent=None if one.parent is None else chains.get(one.parent),
                driver=one.driver,
                loop=loop,
                caps=caps_of(_capabilities(one.driver)),
                declared=caps_of(frozenset(one.declared)),
                facts=_facts(one.driver),
            )
        with self._lock:
            for key, one in self._envs.items():
                if fresh.get(key) is not one:
                    one.open = False
                    # A run over is listed as it last stood, closed; what was destroyed
                    # under a run still going, and an earlier run's, are not listed.
                    if not going and one.run == run:
                        fresh.setdefault(key, one)
            self._envs = fresh
            dying = [term for term in self._terms.values() if not term.env.open]
        for term in dying:
            self._hang_up(term)
        return list(fresh.values())

    def closed(self) -> None:
        """Closes every environment listed, as the host closes: every terminal goes."""
        with self._lock:
            for one in self._envs.values():
                one.open = False
            dying = list(self._terms.values())
        for term in dying:
            self._hang_up(term)

    def _env(self, said: dict[str, Any]) -> _Env:
        key = said.get("env")
        with self._lock:
            env = self._envs.get(key) if isinstance(key, str) else None
        if env is None:
            raise Refused(f"There is no environment {key}.")
        if not env.open:
            raise Refused(_CLOSED)
        return env

    @staticmethod
    def _needs(env: _Env, cap: str) -> None:
        if cap not in env.caps:
            raise Refused(f"{env.role}: this environment has no {cap}.")

    def _browsable(self, env: _Env) -> Browsable:
        self._needs(env, "files")
        driver = env.driver
        if not isinstance(driver, Browsable):
            raise Refused(f"{env.role}: this environment has no files.")
        return driver

    def _on(
        self, env: _Env, work: Coroutine[Any, Any, Any], patience: float = _PATIENCE
    ) -> Any:
        """Runs a coroutine on the environment's loop, waited for from this thread."""
        try:
            done = asyncio.run_coroutine_threadsafe(work, env.loop)
        except RuntimeError:
            work.close()
            raise Refused(_CLOSED) from None
        until = time.monotonic() + patience
        while True:
            try:
                return done.result(timeout=0.25)
            except concurrent.futures.TimeoutError:
                if not env.open or env.loop.is_closed():
                    done.cancel()
                    raise Refused(_CLOSED) from None
                if time.monotonic() > until:
                    done.cancel()
                    raise Refused(
                        f"{env.role}: the environment did not answer in time"
                    ) from None
            except concurrent.futures.CancelledError:
                raise Refused(_CLOSED) from None

    def _exec(
        self, env: _Env, argv: Sequence[str], patience: float = _PATIENCE
    ) -> tuple[int, str, str]:
        self._needs(env, "shell")
        code, out, err = self._on(
            env, env.driver.exec(list(argv), timeout=patience), patience + 5
        )
        return int(code), str(out), str(err)

    def _used(self, env: _Env, by: str, what: str, path: str | None = None) -> None:
        said: dict[str, Any] = {
            "type": "env_used",
            "run": env.run,
            "env": env.id,
            "by": by,
            "what": what,
        }
        if path is not None:
            said["path"] = path
        self._record(said)

    # ------------------------------------------------------------------ requests

    def asked(
        self, client: str, by: str, method: str, said: dict[str, Any]
    ) -> dict[str, Any]:
        """Does one `env.*` request, answering what it answers.

        Args:
          client: The frontend asking.
          by: What it is called, which the history says changes by.
          method: The request, `env.list` and on.
          said: What it said.

        Returns:
          The fields of the answer.

        Raises:
          Refused: Why it was not done, in the words the frontend is told.
        """
        doing = self._doing.get(method)
        if doing is None:
            raise Refused(f"no such request: {method!r}")
        return doing(client, by, said)

    # ------------------------------------------------------------------ files

    def _list(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        entries = self._missing(path, lambda: self._on(env, driver.list(path)))
        listed = sorted(
            (_entry(one) for one in entries),
            key=lambda one: (one["kind"] != "dir", one["name"]),
        )
        return {"path": self._whereabouts(env, path), "entries": listed}

    def _stat(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        found = self._missing(path, lambda: self._on(env, driver.stat(path)))
        return {"path": self._whereabouts(env, path), **_entry(found)}

    def _whereabouts(self, env: _Env, path: str) -> str:
        """A path as an absolute one, a home it is under asked of the env machine."""
        at = _absolute(env.driver.workdir, path)
        driver = env.driver
        # `~/..` is above the home, and written plainly no longer starts with `~`.
        if not at.startswith("/") and isinstance(driver, Homed):
            return str(self._on(env, driver.absolute(path)))
        return at

    @staticmethod
    def _missing[T](path: str, doing: Callable[[], T]) -> T:
        try:
            return doing()
        except FileNotFoundError:
            raise Refused(f"No such file: {path}") from None

    def _file(self, env: _Env, driver: Browsable, path: str) -> Entry:
        """The entry of the file a path is read and written as: where a link leads."""
        at = path
        found = self._missing(path, lambda: self._on(env, driver.stat(path)))
        for _ in range(_HOPS):
            if found.kind != "link" or found.target is None:
                break
            at = posixpath.join(posixpath.dirname(at), found.target)
            found = self._missing(path, lambda at=at: self._on(env, driver.stat(at)))
        return found

    def _whole(
        self, env: _Env, driver: Browsable, path: str
    ) -> tuple[bytes, str, Entry]:
        """A file's bytes and etag, read once for every chunk of it while it stays as it is."""
        found = self._file(env, driver, path)
        if found.kind == "dir":
            raise Refused(f"{path} is a directory")
        key = (
            env.id,
            _absolute(env.driver.workdir, path),
            float(found.mtime),
            int(found.size),
        )
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit[0], hit[1], found
        data = bytes(self._missing(path, lambda: self._on(env, env.driver.read(path))))
        etag = hashlib.sha256(data).hexdigest()
        if len(data) == found.size:
            self._keep(key, data, etag)
        return data, etag, found

    def _keep(self, key: tuple[str, str, float, int], data: bytes, etag: str) -> None:
        """Keeps a file as read, for its next chunk, the oldest kept going first."""
        with self._lock:
            self._forget(key[0], key[1])
            if len(data) > _CACHED:
                return
            self._cache[key] = (data, etag)
            self._cached += len(data)
            while self._cached > _CACHED and self._cache:
                _, (gone, _) = self._cache.popitem(last=False)
                self._cached -= len(gone)

    def _forget(self, env: str, path: str) -> None:
        """Drops what is kept of one file. Under the lock."""
        for key in [key for key in self._cache if key[0] == env and key[1] == path]:
            self._cached -= len(self._cache.pop(key)[0])

    def _read(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        offset = max(0, _int(said, "offset", 0))
        length = min(READ_MAX, max(0, _int(said, "length", READ_MAX)))
        found = self._file(env, driver, path)
        if found.size > _CACHED:
            return self._ranged(env, path, found, offset, length)
        data, etag, found = self._whole(env, driver, path)
        part = data[offset : offset + length]
        return {
            "data": base64.b64encode(part).decode(),
            "size": len(data),
            "mtime": float(found.mtime),
            "etag": etag,
            "eof": offset + len(part) >= len(data),
        }

    def _ranged(
        self, env: _Env, path: str, found: Entry, offset: int, length: int
    ) -> dict[str, Any]:
        """One chunk of a file too large to hold, read where it is, with its etag once."""
        if "shell" not in env.caps:
            raise Refused(f"{path} is too large to read here")
        key = (
            env.id,
            _absolute(env.driver.workdir, path),
            float(found.mtime),
            int(found.size),
        )
        with self._lock:
            etag = self._etags.get(key)
        _, out, err = self._exec(
            env,
            [
                "/bin/sh",
                "-c",
                _RANGE,
                "sh",
                path,
                str(offset),
                str(length),
                "0" if etag else "1",
            ],
        )
        said, _, data = out.partition(".\n")
        if etag is None:
            etag = said.strip()
            if len(etag) != 64:  # noqa: PLR2004 -- a SHA-256 in hexadecimal
                raise Refused(err.strip() or f"{path} could not be read")
            with self._lock:
                self._etags[key] = etag
                while len(self._etags) > 64:  # noqa: PLR2004
                    del self._etags[next(iter(self._etags))]
        part = base64.b64decode(data)
        return {
            "data": base64.b64encode(part).decode(),
            "size": int(found.size),
            "mtime": float(found.mtime),
            "etag": etag,
            "eof": offset + len(part) >= found.size,
        }

    def _write(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        data = _data(said)
        expected = said.get("if_match")
        if expected is not None:
            try:
                found = self._file(env, driver, path)
                if found.size > _CACHED:
                    etag = self._ranged(env, path, found, 0, 0)["etag"]
                else:
                    _, etag, _ = self._whole(env, driver, path)
            except Refused as why:
                if not str(why).startswith("No such file"):
                    raise
                etag = ""
            if etag != expected:
                raise Refused(f"{path} changed since you read it.")
        self._on(env, env.driver.write(path, data))
        found = self._file(env, driver, path)
        etag = hashlib.sha256(data).hexdigest()
        key = (
            env.id,
            _absolute(env.driver.workdir, path),
            float(found.mtime),
            len(data),
        )
        self._keep(key, data, etag)
        self._used(env, by, "wrote", path)
        return {"etag": etag, "size": len(data), "mtime": float(found.mtime)}

    def _mkdir(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        self._on(env, driver.mkdir(path))
        self._used(env, by, "made", path)
        return {}

    def _rename(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        to = said.get("to")
        if not isinstance(to, str) or not to:
            raise Refused("where to rename it to is said")
        self._missing(path, lambda: self._on(env, driver.rename(path, to)))
        with self._lock:
            self._forget(env.id, _absolute(env.driver.workdir, path))
        self._used(env, by, "renamed", path)
        return {}

    def _remove(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client
        env = self._env(said)
        driver = self._browsable(env)
        path = _path(said)
        self._missing(path, lambda: self._on(env, driver.remove(path)))
        with self._lock:
            self._forget(env.id, _absolute(env.driver.workdir, path))
        self._used(env, by, "removed", path)
        return {}

    def _find(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        driver = self._browsable(env)
        limit = min(_FIND_MOST, max(1, _int(said, "limit", 20_000)))
        if "shell" not in env.caps:
            return self._walked(env, driver, limit)
        _, out, _ = self._exec(env, ["/bin/sh", "-c", _FIND, "sh", str(_LISTED)])
        paths = list(
            dict.fromkeys(one.removeprefix("./") for one in out.split("\0")[:-1] if one)
        )
        cut = len(out.encode()) >= _LISTED or len(paths) > limit
        return {"paths": paths[:limit], "truncated": cut}

    def _walked(self, env: _Env, driver: Browsable, limit: int) -> dict[str, Any]:
        """Every file under the workdir, listed a directory at a time where there is no shell."""
        paths: list[str] = []
        waiting = collections.deque([""])
        while waiting and len(paths) <= limit:
            under = waiting.popleft()
            with contextlib.suppress(Exception):
                for one in self._on(env, driver.list(under or ".")):
                    path = f"{under}/{one.name}" if under else one.name
                    if one.kind == "dir":
                        if one.name not in {".git", "node_modules"}:
                            waiting.append(path)
                    else:
                        paths.append(path)
        return {
            "paths": paths[:limit],
            "truncated": len(paths) > limit or bool(waiting),
        }

    def _search(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        self._browsable(env)
        if "shell" not in env.caps:
            raise Refused(f"{env.role}: this environment has no files.")
        query = said.get("query")
        if not isinstance(query, str) or not query:
            raise Refused("what to search for is said")
        regex = bool(said.get("regex"))
        exact = bool(said.get("case"))
        glob = said.get("glob") or ""
        if not isinstance(glob, str):
            raise Refused("glob is a pattern")
        limit = min(_SEARCH_MOST, max(1, _int(said, "limit", 2000)))
        _, out, _ = self._exec(
            env,
            [
                "/bin/sh",
                "-c",
                _SEARCH,
                "sh",
                query,
                "E" if regex else "F",
                "s" if exact else "i",
                glob,
                # rg says a file begins and ends around its matches: room for those.
                str(limit * 3 + 64),
            ],
        )
        tool, _, rest = out.partition("\n")
        if tool.strip() == "rg":
            matches = _rg(rest, limit + 1)
        else:
            matches = _grep(rest, query, regex=regex, exact=exact, limit=limit + 1)
        return {"matches": matches[:limit], "truncated": len(matches) > limit}

    # ------------------------------------------------------------------ terminals

    def _term_open(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        env = self._env(said)
        cols = max(1, _int(said, "cols", 80))
        rows = max(1, _int(said, "rows", 24))
        self._needs(env, "shell")
        driver = env.driver
        if not isinstance(driver, Terminable):
            raise Refused(f"{env.role}: this environment has no shell.")
        again = said.get("term")
        if again is not None:
            return self._reattach(client, env, str(again), cols, rows)
        # The env machine's login shell, which the driver picks there.
        pty: Pty = self._on(env, driver.pty(None, cols=cols, rows=rows))
        term = _Term(
            id=f"t{next(self._counted)}",
            env=env,
            cols=cols,
            rows=rows,
            pty=pty,
            room=asyncio.Event(),
        )
        term.viewers[client] = _Viewer()
        with self._lock:
            self._terms[term.id] = term
            closed = not env.open
        if closed:
            self._hang_up(term)
            raise Refused(_CLOSED)
        try:
            asyncio.run_coroutine_threadsafe(self._reads(term), env.loop)
        except RuntimeError:
            self._hang_up(term)
            raise Refused(_CLOSED) from None
        self._used(env, by, "opened a terminal")
        return {"term": term.id, "shell": term.shell, "replay": ""}

    def _reattach(
        self, client: str, env: _Env, key: str, cols: int, rows: int
    ) -> dict[str, Any]:
        with self._lock:
            term = self._terms.get(key)
            if term is None or term.env is not env:
                raise Refused(f"There is no terminal {key}.")
            term.viewers[client] = _Viewer()
            replay = bytes(term.scroll)
            exited = None if term.alive else term.status
        self._rooms(term)
        if exited is not None:
            self._post(client, {"type": "term_exit", "term": term.id, "status": exited})
        elif (cols, rows) != (term.cols, term.rows):
            with contextlib.suppress(Refused):
                self._resized(term, cols, rows)
        return {
            "term": term.id,
            "shell": term.shell,
            "replay": base64.b64encode(replay).decode(),
        }

    def _term(self, said: dict[str, Any]) -> _Term:
        key = said.get("term")
        with self._lock:
            term = self._terms.get(key) if isinstance(key, str) else None
        if term is None:
            raise Refused(f"There is no terminal {key}.")
        return term

    def _term_input(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        term = self._term(said)
        data = _data(said)
        if term.alive and data:
            self._on(term.env, term.pty.write(data))
        return {}

    def _term_resize(
        self, client: str, by: str, said: dict[str, Any]
    ) -> dict[str, Any]:
        del client, by
        term = self._term(said)
        self._resized(
            term,
            max(1, _int(said, "cols", term.cols)),
            max(1, _int(said, "rows", term.rows)),
        )
        return {}

    def _resized(self, term: _Term, cols: int, rows: int) -> None:
        term.cols, term.rows = cols, rows
        if term.alive:
            self._on(term.env, term.pty.resize(cols, rows))

    def _term_ack(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del by
        term = self._term(said)
        count = max(0, _int(said, "bytes", 0))
        with self._lock:
            viewer = term.viewers.get(client)
            if viewer is not None:
                viewer.unacked = max(0, viewer.unacked - count)
                more = bool(viewer.pending)
            else:
                more = False
        self._rooms(term)
        if more:
            self._soon(term, self._flush, term)
        return {}

    def _term_close(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        term = self._term(said)
        with self._lock:
            self._terms.pop(term.id, None)
        self._soon(term, term.room.set)
        if term.alive:
            with contextlib.suppress(Refused):
                self._on(term.env, term.pty.kill(), 15.0)
        else:
            self._told_exit(term)
        return {}

    def _term_list(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        with self._lock:
            terms = [one for one in self._terms.values() if one.env is env]
        return {
            "terms": [
                {
                    "term": one.id,
                    "env": env.id,
                    "title": one.title,
                    "cols": one.cols,
                    "rows": one.rows,
                    "alive": one.alive,
                }
                for one in terms
            ]
        }

    def let_go(self, client: str) -> None:
        """Stops showing every terminal to a frontend that has gone. The terminals live on."""
        with self._lock:
            terms = [one for one in self._terms.values() if client in one.viewers]
            for one in terms:
                del one.viewers[client]
                if not one.viewers:
                    one.alone_since = time.monotonic()
        for one in terms:
            self._rooms(one)

    def tick(self) -> None:
        """Takes away every terminal nobody has watched for :data:`IDLE` seconds."""
        now = time.monotonic()
        with self._lock:
            idle = [
                one
                for one in self._terms.values()
                if not one.viewers and (not one.alive or now - one.alone_since > IDLE)
            ]
            for one in idle:
                del self._terms[one.id]
        for one in idle:
            if one.alive:
                self._killed(one)

    async def _reads(self, term: _Term) -> None:
        """Reads a terminal until it ends, handing what it prints to whoever watches it."""
        loop = asyncio.get_running_loop()
        with contextlib.suppress(Exception):
            while True:
                while True:
                    with self._lock:
                        # One closed is read out to its end, whoever has room.
                        roomy = term.roomy or self._terms.get(term.id) is not term
                    if roomy:
                        break
                    # Woken by whoever makes room (:meth:`_rooms`), from any thread.
                    term.room.clear()
                    await term.room.wait()
                data = await term.pty.read()
                if not data:
                    break
                with self._lock:
                    term.scroll += data
                    if len(term.scroll) > SCROLLBACK:
                        del term.scroll[: len(term.scroll) - SCROLLBACK]
                    for viewer in term.viewers.values():
                        viewer.pending += data
                        if len(viewer.pending) > _BEHIND:
                            del viewer.pending[: len(viewer.pending) - _BEHIND]
                    later = not term.flushing
                    term.flushing = True
                if later:
                    loop.call_later(COALESCE, self._flush, term)
                self._rooms(term)
                # Let whatever else is waiting on the loop go between two reads.
                await asyncio.sleep(0)
        status = -1
        with contextlib.suppress(Exception):
            status = int(await term.pty.wait())
        with self._lock:
            term.alive = False
            if term.status is None:
                term.status = status
        self._flush(term)
        self._told_exit(term)

    def _flush(self, term: _Term) -> None:
        """Sends each viewer what it has room for, a chunk at a time."""
        sending: list[tuple[str, dict[str, Any]]] = []
        with self._lock:
            term.flushing = False
            for client, viewer in term.viewers.items():
                while viewer.pending and viewer.unacked < CREDIT:
                    chunk = bytes(viewer.pending[:CHUNK])
                    del viewer.pending[:CHUNK]
                    viewer.unacked += len(chunk)
                    sending.append(
                        (
                            client,
                            {
                                "type": "term",
                                "term": term.id,
                                "data": base64.b64encode(chunk).decode(),
                            },
                        )
                    )
        for client, message in sending:
            with contextlib.suppress(Exception):
                self._post(client, message)
        self._rooms(term)

    def _rooms(self, term: _Term) -> None:
        """Lets the terminal be read while somebody has room for more of it, or nobody watches."""
        with self._lock:
            roomy = not term.viewers or any(
                one.unacked + len(one.pending) < CREDIT for one in term.viewers.values()
            )
            changed = roomy != term.roomy
            term.roomy = roomy
        if changed and roomy:
            self._soon(term, term.room.set)

    @staticmethod
    def _soon(term: _Term, doing: Callable[..., object], *args: Any) -> None:
        with contextlib.suppress(RuntimeError):
            term.env.loop.call_soon_threadsafe(doing, *args)

    def _told_exit(self, term: _Term) -> None:
        """Tells each viewer a terminal has ended, the once."""
        with self._lock:
            if term.told_exit:
                return
            term.told_exit = True
            viewers = list(term.viewers)
            status = term.status if term.status is not None else -1
        for client in viewers:
            with contextlib.suppress(Exception):
                self._post(
                    client, {"type": "term_exit", "term": term.id, "status": status}
                )

    def _killed(self, term: _Term) -> None:
        """Kills a terminal without waiting for it to go."""
        with contextlib.suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(term.pty.kill(), term.env.loop)

    def _hang_up(self, term: _Term) -> None:
        """Kills a terminal whose environment closed, and says so to whoever watches it."""
        with self._lock:
            self._terms.pop(term.id, None)
            alive = term.alive
            term.alive = False
            if term.status is None:
                term.status = _HUNG_UP
        self._soon(term, term.room.set)
        if alive:
            self._killed(term)
        self._told_exit(term)

    # ------------------------------------------------------------------ git

    def _git(self, env: _Env) -> tuple[gitdesk.Exec, str]:
        if "git" not in env.caps and "git_worktree" not in env.caps:
            raise Refused(f"{env.role}: this environment has no git.")

        async def exec_(argv: Sequence[str]) -> tuple[int, str, str]:
            return await env.driver.exec(list(argv), timeout=_PATIENCE)

        top = env.top
        if top is None:
            try:
                top = self._on(env, gitdesk.root(exec_), _PATIENCE + 5)
            except gitdesk.GitError:
                # A workdir in no repository has no git to work, as one without git has none.
                raise Refused(f"{env.role}: this environment has no git.") from None
            env.top = top
        return exec_, top

    def _gitting(self, env: _Env, work: Coroutine[Any, Any, Any]) -> Any:
        try:
            return self._on(env, work, _PATIENCE + 5)
        except gitdesk.GitError as why:
            raise Refused(str(why)) from None

    def _git_status(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        exec_, top = self._git(env)
        return self._gitting(env, gitdesk.status(exec_, top))

    def _git_diff(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        exec_, top = self._git(env)
        return self._gitting(
            env, gitdesk.diff(exec_, top, _path(said), staged=bool(said.get("staged")))
        )

    def _git_log(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        exec_, top = self._git(env)
        limit = min(1000, max(1, _int(said, "limit", 50)))
        return {"commits": self._gitting(env, gitdesk.log(exec_, top, limit))}

    def _git_paths(
        self,
        doing: Callable[[gitdesk.Exec, str, Sequence[str]], Coroutine[Any, Any, None]],
        what: str,
    ) -> Callable[[str, str, dict[str, Any]], dict[str, Any]]:
        def answers(client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
            del client
            env = self._env(said)
            exec_, top = self._git(env)
            paths = _paths(said)
            self._gitting(env, doing(exec_, top, paths))
            self._used(env, by, what, paths[0] if len(paths) == 1 else None)
            return {}

        return answers

    def _git_commit(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client
        env = self._env(said)
        exec_, top = self._git(env)
        message = said.get("message") or ""
        if not isinstance(message, str):
            raise Refused("the message is text")
        amend = bool(said.get("amend"))
        if not message.strip():
            raise Refused("a commit needs a message")
        head = self._gitting(env, gitdesk.commit(exec_, top, message, amend=amend))
        self._used(env, by, "committed")
        return {"head": head}

    def _rewinds(self, env: _Env) -> Any:
        if "rewind" not in env.caps:
            raise Refused(f"{env.role}: this environment has no git.")
        return env.driver

    def _git_snapshots(
        self, client: str, by: str, said: dict[str, Any]
    ) -> dict[str, Any]:
        del client, by
        env = self._env(said)
        driver = self._rewinds(env)
        try:
            refs = self._on(env, driver.snapshots())
        except Refused:
            raise
        except Exception as why:  # noqa: BLE001 -- not a worktree, said as git said it
            raise Refused(str(why) or type(why).__name__) from None
        return {"snapshots": [str(one) for one in refs]}

    def _git_rewind(self, client: str, by: str, said: dict[str, Any]) -> dict[str, Any]:
        del client
        env = self._env(said)
        driver = self._rewinds(env)
        ref = said.get("ref")
        if not isinstance(ref, str) or not ref:
            raise Refused("what to rewind to is said")
        working = self._guard(env.run, env.driver)
        if working is not None:
            raise Refused(f"{working} is working here; stop it first")
        try:
            self._on(env, driver.rewind(ref))
        except Refused:
            raise
        except Exception as why:  # noqa: BLE001 -- an unknown ref, said as git said it
            raise Refused(str(why) or type(why).__name__) from None
        self._used(env, by, "rewound")
        return {}


# ---------------------------------------------------------------------------- helpers


def _capabilities(driver: Any) -> frozenset[type]:
    try:
        return frozenset(driver.capabilities)
    except Exception:  # noqa: BLE001 -- a driver that cannot say serves nothing
        return frozenset()


def _int(said: dict[str, Any], key: str, default: int) -> int:
    value = said.get(key, default)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise Refused(f"{key} is a number")
    return int(value)


def _path(said: dict[str, Any]) -> str:
    path = said.get("path")
    if path is None or path == "":
        return "."
    if not isinstance(path, str):
        raise Refused("path is text")
    return path


def _paths(said: dict[str, Any]) -> list[str]:
    paths = said.get("paths")
    if (
        not isinstance(paths, list)
        or not paths
        or not all(isinstance(one, str) and one for one in paths)  # pyright: ignore[reportUnknownVariableType]
    ):
        raise Refused("paths are a list of paths")
    return list(paths)  # pyright: ignore[reportUnknownArgumentType]


def _data(said: dict[str, Any]) -> bytes:
    data = said.get("data")
    if not isinstance(data, str):
        raise Refused("data is base64")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise Refused("data is base64") from None


def _absolute(workdir: PurePosixPath | str, path: str) -> str:
    """Where a path is, said whole: as given where it is absolute, else under the workdir."""
    if path.startswith(("/", "~")):
        return posixpath.normpath(path)
    return posixpath.normpath(posixpath.join(str(workdir), path))


def _entry(one: Entry) -> dict[str, Any]:
    said: dict[str, Any] = {
        "name": one.name,
        "kind": one.kind,
        "size": int(one.size),
        "mtime": float(one.mtime),
    }
    if one.target is not None:
        said["target"] = one.target
    return said


def _rg(text: str, limit: int) -> list[dict[str, Any]]:
    """The matches `rg --json` printed, one per line matched."""
    found: list[dict[str, Any]] = []
    for line in text.splitlines():
        if len(found) >= limit:
            break
        try:
            said: Any = json.loads(line)
        except ValueError:
            continue
        if not isinstance(said, dict):
            continue
        message = cast("dict[str, Any]", said)
        if message.get("type") != "match":
            continue
        data = cast("dict[str, Any]", message.get("data") or {})
        path = _text(data.get("path"))
        text_bytes = _bytes(data.get("lines"))
        column = 1
        submatches = cast("list[dict[str, Any]]", data.get("submatches") or [])
        if submatches:
            start = int(submatches[0].get("start", 0))
            column = len(text_bytes[:start].decode(errors="replace")) + 1
        found.append(
            {
                "path": path.removeprefix("./"),
                "line": int(data.get("line_number") or 0),
                "column": column,
                "text": text_bytes.decode(errors="replace").rstrip("\r\n")[:_LINE],
            }
        )
    return found


def _text(said: Any) -> str:
    return _bytes(said).decode(errors="replace")


def _bytes(said: Any) -> bytes:
    """What `rg --json` says as `{"text": ...}`, or as `{"bytes": base64}` where not UTF-8."""
    if not isinstance(said, dict):
        return b""
    if "text" in said:
        return str(said["text"]).encode()  # pyright: ignore[reportUnknownArgumentType]
    with contextlib.suppress(binascii.Error, ValueError):
        return base64.b64decode(str(said.get("bytes", "")))  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
    return b""


def _grep(
    text: str, query: str, *, regex: bool, exact: bool, limit: int
) -> list[dict[str, Any]]:
    """The matches `grep -rn` printed: `./path:line:text`."""
    pattern: re.Pattern[str] | None = None
    with contextlib.suppress(re.error):
        pattern = re.compile(
            query if regex else re.escape(query), 0 if exact else re.IGNORECASE
        )
    found: list[dict[str, Any]] = []
    for line in text.splitlines():
        if len(found) >= limit:
            break
        path, sep, rest = line.partition(":")
        number, sep2, said = rest.partition(":")
        if not sep or not sep2 or not number.isdigit():
            continue
        hit = pattern.search(said) if pattern is not None else None
        found.append(
            {
                "path": path.removeprefix("./"),
                "line": int(number),
                "column": hit.start() + 1 if hit is not None else 1,
                "text": said[:_LINE],
            }
        )
    return found
