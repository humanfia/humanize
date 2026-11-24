r"""A host's environments: files, terminals and git (`env.*`, `hosts.env.*`).

An environment is where the agents of an epic or a chat work: a directory of some machine,
which its host reaches for them. There are two ways to it, as the daemon has two.

The envs of the epic going on a host are reached by the role each has in its flow, without
attaching (`hosts.env.*`): :meth:`Envs.list`, :meth:`Envs.read`, :meth:`Envs.write`,
:meth:`Envs.exec` and :meth:`Envs.grep`, which do what the flow itself could.

Everything the page's environment panels do is done as a frontend of the host (`env.*`), so
:meth:`Envs.attached` attaches as one and answers what it sees from there::

    with client.envs.attached("/path/to/project") as host:
        env = host.env()                      # the first environment that is open
        for entry in env.files.list("."):
            print(entry.kind, entry.name)
        read = env.files.read("README.md")
        env.files.write("README.md", read.data + b"more\n", if_match=read.etag)
        env.git.stage(["README.md"])
        env.git.commit("docs: say more")
        with env.terminals.open(cols=120, rows=40) as terminal:
            terminal.write("make test; exit\n")
            for printed in terminal:
                sys.stdout.buffer.write(printed)
"""

from __future__ import annotations

import base64
import contextlib
import queue
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self

from . import Family

if TYPE_CHECKING:
    import builtins
    from collections.abc import Iterator, Mapping, Sequence
    from types import TracebackType

    from . import Subscription

__all__ = [
    "ACK_EVERY",
    "Attached",
    "Change",
    "Commit",
    "Diff",
    "Entry",
    "Env",
    "EnvFiles",
    "EnvGit",
    "EnvTerminals",
    "Environment",
    "Envs",
    "Found",
    "Grepped",
    "Line",
    "Match",
    "Ran",
    "Read",
    "Role",
    "Searched",
    "Shell",
    "Status",
    "Terminal",
    "Text",
    "Wrote",
]

#: How many bytes of a terminal's output are read before the host is told they were: it sends
#: no more while a mebibyte is unacknowledged (Section 4.24.4.6 of daemon.md).
ACK_EVERY = 64 * 1024

#: The most one `env.read` answers, which is what a file is read whole in pieces of.
_CHUNK = 1024 * 1024

#: How long a host is given to say how it stands once attached to.
_PATIENCE = 30.0


class _Ask(Protocol):
    """One call to a host, with what names the subscription or the environment already in."""

    def __call__(
        self,
        method: str,
        /,
        *,
        idem: str | None = None,
        wait: float | None = None,
        **params: Any,
    ) -> Any: ...


def _refused(message: str, code: int) -> Exception:
    from hmz.sdk import Refused

    return Refused(message, code=code)


def _bytes(data: object) -> bytes:
    return base64.b64decode(data) if isinstance(data, str) else b""


def _text(data: bytes | str) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return base64.b64encode(raw).decode("ascii")


# -- What is answered ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Role:
    """One env of the epic going on a host, as its flow names it."""

    name: str
    """The role it has in the flow, which the `hosts.env.*` calls take as `env`."""
    kind: str
    """What kind of env it is: `local`, `docker`, `ssh`, ..."""
    workdir: str
    """Where it works, on its machine."""
    can: tuple[str, ...]
    """Those of `read`, `write`, `exec` and `grep` it offers."""


@dataclass(frozen=True)
class Text:
    """A file of an env read as text."""

    text: str
    """What was read, as UTF-8, each byte that is not replaced by U+FFFD."""
    size: int
    """How long the whole file is, in bytes."""
    eof: bool
    """Whether what was read reaches its end."""


@dataclass(frozen=True)
class Ran:
    """A command run in an env."""

    code: int | None
    """Its exit status, None where it was killed once its time had passed."""
    stdout: str
    """The last mebibyte it wrote to standard output."""
    stderr: str
    """The last mebibyte it wrote to standard error."""


@dataclass(frozen=True)
class Line:
    """One line `hosts.env.grep` found."""

    path: str
    """The file, relative to the workdir."""
    line: int
    """Which line of it, from 1."""
    text: str
    """The line, cut at 400 characters."""


@dataclass(frozen=True)
class Grepped:
    """What `hosts.env.grep` found."""

    matches: tuple[Line, ...]
    more: bool
    """Whether there were more than were asked for."""


@dataclass(frozen=True)
class Env:
    """One environment of a host, as its `envs` snapshot describes it."""

    id: str
    """What the host knows it by, the same for the life of the host; nothing is read into it."""
    role: str
    """The role it has in the flow."""
    chain: str
    """Its label: its role, then each derivation that made it."""
    parent: str | None
    """The `id` of the environment it was derived from, None for a root one."""
    run: int
    """The number of the epic it is of."""
    backend: str
    """Its kind: `local`, `docker`, `ssh`, ..."""
    provider: str
    """The runtime it is on."""
    workdir: str
    """Where it works, on its machine."""
    available: bool
    """Whether the calls here reach it at all."""
    open: bool
    """Whether it is open; a closed one is listed and refuses everything."""
    caps: tuple[str, ...]
    """What it serves, of `files`, `shell`, `bash`, `git`, `git_worktree`, `rewind`,
    `scratch` and `temp_clone`."""
    declared: tuple[str, ...]
    """What its role declares, of the same names."""
    facts: dict[str, Any]
    """`cpu`, `memory`, `gpu_count` and `gpu_memory` as its probe found them."""


@dataclass(frozen=True)
class Entry:
    """One path of an environment."""

    name: str
    kind: str
    """`file`, `dir`, `link` or `other`."""
    size: int
    """Its length in bytes."""
    mtime: float
    """When it last changed, in seconds since the epoch."""
    path: str | None = None
    """It as an absolute path, where it was asked for by itself."""
    target: str | None = None
    """What a link points at."""


@dataclass(frozen=True)
class Read:
    """A file of an environment, or a piece of it, as it was read."""

    data: bytes
    size: int
    """How long the whole file is."""
    mtime: float
    etag: str
    """The SHA-256 of the whole file, which a write is made against (`if_match`)."""
    eof: bool
    """Whether `data` reaches the end of the file."""


@dataclass(frozen=True)
class Wrote:
    """A file of an environment as a write left it."""

    etag: str
    size: int
    mtime: float


@dataclass(frozen=True)
class Found:
    """The files of an environment, to open one by its name."""

    paths: tuple[str, ...]
    """Each relative to the workdir."""
    truncated: bool
    """Whether there were more than were asked for."""


@dataclass(frozen=True)
class Match:
    """One place a search found its text."""

    path: str
    line: int
    """From 1."""
    column: int
    """From 1."""
    text: str
    """The line."""


@dataclass(frozen=True)
class Searched:
    """What a search of an environment found."""

    matches: tuple[Match, ...]
    truncated: bool
    """Whether there were more than were asked for."""


@dataclass(frozen=True)
class Change:
    """One changed path of a repository."""

    path: str
    """Relative to the repository's top directory."""
    index: str
    """What the index has of it: the `X` of `git status --porcelain=v2`, `.` for unchanged
    and `?` for untracked."""
    worktree: str
    """What the worktree has of it: the `Y`, read the same way."""
    state: str
    """`changed`, `untracked` or `conflict`."""
    orig: str | None = None
    """Where it was renamed or copied from, where it was."""


@dataclass(frozen=True)
class Status:
    """The git status of an environment."""

    root: str
    """The repository's top directory."""
    branch: str | None
    """The branch checked out, None where none is."""
    head: str | None
    """The commit checked out, None before the first."""
    upstream: str | None
    ahead: int
    behind: int
    files: tuple[Change, ...]


@dataclass(frozen=True)
class Diff:
    """Both sides of one file's change."""

    old: bytes | None
    """The file before: the index, or with `staged` the commit checked out; None where
    that side has no such file."""
    new: bytes | None
    """The file after: the worktree, or with `staged` the index."""
    binary: bool
    """Whether git reads either side as binary."""


@dataclass(frozen=True)
class Commit:
    """One commit of an environment's repository."""

    hash: str
    parents: tuple[str, ...]
    author: str
    date: str
    """ISO 8601."""
    subject: str


@dataclass(frozen=True)
class Shell:
    """One terminal of an environment, as the host lists it."""

    term: str
    """Its id, which :meth:`EnvTerminals.open` comes back to it by."""
    env: str
    title: str
    cols: int
    rows: int
    alive: bool
    """Whether it still runs; one that ended is listed while a frontend views it."""


def _entry(said: Mapping[str, Any]) -> Entry:
    return Entry(
        str(said["name"]),
        str(said["kind"]),
        int(said["size"]),
        float(said["mtime"]),
        said.get("path"),
        said.get("target"),
    )


def _env(said: Mapping[str, Any]) -> Env:
    return Env(
        id=str(said["id"]),
        role=str(said.get("role") or ""),
        chain=str(said.get("chain") or said.get("role") or ""),
        parent=said.get("parent"),
        run=int(said.get("run") or 0),
        backend=str(said.get("backend") or ""),
        provider=str(said.get("provider") or ""),
        workdir=str(said.get("workdir") or ""),
        available=bool(said.get("available")),
        open=bool(said.get("open")),
        caps=tuple(said.get("caps") or ()),
        declared=tuple(said.get("declared") or ()),
        facts=dict(said.get("facts") or {}),
    )


# -- One environment, as a frontend of its host --------------------------------------------------


class EnvFiles:
    """The files of one environment (`env.list` to `env.remove`).

    A path is relative to the environment's workdir, or an absolute path of its machine.
    """

    def __init__(self, ask: _Ask) -> None:
        """Made by :class:`Environment`."""
        self._ask = ask

    def list(self, path: str = ".") -> builtins.list[Entry]:
        """The entries of a directory, directories first and then by name."""
        return [_entry(one) for one in self._ask("env.list", path=path)["entries"]]

    def stat(self, path: str) -> Entry:
        """What one path is, with `path` as an absolute path.

        Raises:
          hmz.sdk.Refused: `No such file: <path>` where it names nothing.
        """
        return _entry(self._ask("env.stat", path=path))

    def read(
        self, path: str, *, offset: int | None = None, length: int | None = None
    ) -> Read:
        """Reads a file: all of it, or the piece asked for.

        Args:
          path: The file.
          offset: Where to read from, None for its start.
          length: How many bytes to read, at most 1048576; None, with no `offset`, for the
            whole file however long, read a mebibyte at a time.

        Returns:
          What was read, and the `etag` of the whole file as it was then.

        Raises:
          hmz.sdk.Refused: Where the host refuses, or the file kept changing while read.
        """
        if offset is not None or length is not None:
            return self._piece(path, offset, length)
        for _ in range(3):
            pieces: list[bytes] = []
            first = last = self._piece(path, 0, _CHUNK)
            pieces.append(first.data)
            while not last.eof and last.data and last.etag == first.etag:
                last = self._piece(path, sum(map(len, pieces)), _CHUNK)
                pieces.append(last.data)
            if last.etag == first.etag:
                return Read(
                    b"".join(pieces), last.size, last.mtime, last.etag, eof=True
                )
        raise _refused(f"{path} kept changing while it was read", 409)

    def _piece(self, path: str, offset: int | None, length: int | None) -> Read:
        said = self._ask("env.read", path=path, offset=offset, length=length)
        return Read(
            _bytes(said["data"]),
            int(said["size"]),
            float(said["mtime"]),
            str(said["etag"]),
            bool(said["eof"]),
        )

    def find(self, *, limit: int | None = None) -> Found:
        """The files of the workdir, as many as `limit` (20000 where None).

        In a git repository these are the files git tracks or does not ignore; elsewhere
        every file but those under `.git` or `node_modules`.
        """
        said = self._ask("env.find", limit=limit)
        return Found(tuple(said["paths"]), bool(said["truncated"]))

    def search(
        self,
        query: str,
        *,
        regex: bool | None = None,
        case: bool | None = None,
        glob: str | None = None,
        limit: int | None = None,
    ) -> Searched:
        """Searches the files :meth:`find` lists for text.

        Args:
          query: What to look for.
          regex: Whether `query` is a regular expression rather than literal text.
          case: Whether case counts.
          glob: The glob a file's path has to match.
          limit: The most matches answered, 2000 where None.
        """
        said = self._ask(
            "env.search", query=query, regex=regex, case=case, glob=glob, limit=limit
        )
        return Searched(
            tuple(
                Match(
                    str(one["path"]),
                    int(one["line"]),
                    int(one["column"]),
                    str(one["text"]),
                )
                for one in said["matches"]
            ),
            bool(said["truncated"]),
        )

    def write(
        self,
        path: str,
        data: bytes | str,
        *,
        if_match: str | None = None,
        idem: str | None = None,
    ) -> Wrote:
        """Makes a file hold exactly `data`.

        Args:
          path: The file.
          data: What it is to hold; text is written as UTF-8.
          if_match: None to write whatever the file holds; `""` to write only where there
            is no file yet; an `etag` to write only where the file is still as it was read.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: `<path> changed since you read it.` where `if_match` does not
            hold, which leaves the file as it was.
        """
        said = self._ask(
            "env.write", path=path, data=_text(data), if_match=if_match, idem=idem
        )
        return Wrote(str(said["etag"]), int(said["size"]), float(said["mtime"]))

    def mkdir(self, path: str, *, idem: str | None = None) -> None:
        """Makes a directory, and every missing directory above it."""
        self._ask("env.mkdir", path=path, idem=idem)

    def rename(self, path: str, to: str, *, idem: str | None = None) -> None:
        """Moves a path to another."""
        self._ask("env.rename", path=path, to=to, idem=idem)

    def remove(self, path: str, *, idem: str | None = None) -> None:
        """Removes a path, and everything under it."""
        self._ask("env.remove", path=path, idem=idem)


class EnvGit:
    """The git repository one environment's workdir is in (`env.git.*`).

    Every call is refused with `<role>: this environment has no git.` where there is none.
    """

    def __init__(self, ask: _Ask) -> None:
        """Made by :class:`Environment`."""
        self._ask = ask

    def status(self) -> Status:
        """Where the repository stands: its branch, its upstream, and every changed path."""
        said = self._ask("env.git.status")
        return Status(
            root=str(said["root"]),
            branch=said.get("branch"),
            head=said.get("head"),
            upstream=said.get("upstream"),
            ahead=int(said.get("ahead") or 0),
            behind=int(said.get("behind") or 0),
            files=tuple(
                Change(
                    str(one["path"]),
                    str(one["index"]),
                    str(one["worktree"]),
                    str(one["state"]),
                    one.get("orig"),
                )
                for one in said["files"]
            ),
        )

    def diff(self, path: str, *, staged: bool | None = None) -> Diff:
        """Both sides of one file's change.

        Args:
          path: The file.
          staged: Whether to compare the commit checked out with the index, rather than
            the index with the worktree.
        """
        said = self._ask("env.git.diff", path=path, staged=staged)
        old, new = said.get("old"), said.get("new")
        return Diff(
            None if old is None else _bytes(old),
            None if new is None else _bytes(new),
            bool(said["binary"]),
        )

    def log(self, *, limit: int | None = None) -> list[Commit]:
        """The latest commits from the one checked out, newest first; 50 where `limit` is None."""
        return [
            Commit(
                str(one["hash"]),
                tuple(one["parents"]),
                str(one["author"]),
                str(one["date"]),
                str(one["subject"]),
            )
            for one in self._ask("env.git.log", limit=limit)["commits"]
        ]

    def stage(self, paths: Sequence[str], *, idem: str | None = None) -> None:
        """Adds paths to the index, removals included."""
        self._ask("env.git.stage", paths=list(paths), idem=idem)

    def unstage(self, paths: Sequence[str], *, idem: str | None = None) -> None:
        """Makes the index of paths that of the commit checked out."""
        self._ask("env.git.unstage", paths=list(paths), idem=idem)

    def discard(self, paths: Sequence[str], *, idem: str | None = None) -> None:
        """Makes the worktree of paths that of the index, and removes the untracked ones."""
        self._ask("env.git.discard", paths=list(paths), idem=idem)

    def commit(
        self, message: str, *, amend: bool | None = None, idem: str | None = None
    ) -> str:
        """Commits the index.

        Args:
          message: The commit's message.
          amend: Whether to amend the commit checked out rather than add one.
          idem: The key this is done once under.

        Returns:
          The new commit.
        """
        said = self._ask("env.git.commit", message=message, amend=amend, idem=idem)
        return str(said["head"])

    def snapshots(self) -> list[str]:
        """The snapshot refs of the environment, which :meth:`rewind` takes."""
        return [str(one) for one in self._ask("env.git.snapshots")["snapshots"]]

    def rewind(self, ref: str, *, idem: str | None = None) -> None:
        """Rewinds the environment to a snapshot: every change since is lost.

        Raises:
          hmz.sdk.Refused: `<role> is working here; stop it first` while a session working
            in the environment has a turn open.
        """
        self._ask("env.git.rewind", ref=ref, idem=idem)


class _Terms:
    """What a host's terminals say to this frontend, kept a terminal apiece until it is read.

    A terminal speaks from the moment it starts, which is before the answer saying which it
    is; and one this frontend has left is still one it views, which the host stops once a
    mebibyte of it goes unacknowledged. So what a terminal says is kept from the first of it,
    and what one that was left says is acknowledged here and dropped.
    """

    def __init__(self, ask: _Ask) -> None:
        self._ask = ask
        self._lock = threading.Lock()
        self._held: dict[str, queue.SimpleQueue[Mapping[str, Any] | None]] = {}
        self._left: dict[str, int] = {}
        self._closed = False

    def told(self, message: Mapping[str, Any]) -> None:
        """Takes one `term` or `term_exit` the host sent."""
        term = str(message.get("term") or "")
        acked = 0
        with self._lock:
            if term not in self._left:
                self._inbox(term).put(message)
                return
            if message.get("type") == "term_exit":
                del self._left[term]
                return
            self._left[term] += len(_bytes(message.get("data")))
            if self._left[term] >= ACK_EVERY:
                acked, self._left[term] = self._left[term], 0
        if acked:
            with contextlib.suppress(Exception):
                self._ask("env.term.ack", term=term, bytes=acked)

    def _inbox(self, term: str) -> queue.SimpleQueue[Mapping[str, Any] | None]:
        inbox = self._held.get(term)
        if inbox is None:
            inbox = self._held[term] = queue.SimpleQueue()
            if self._closed:
                inbox.put(None)
        return inbox

    def inbox(self, term: str) -> queue.SimpleQueue[Mapping[str, Any] | None]:
        """Where one terminal's messages are, from the first of them."""
        with self._lock:
            return self._inbox(term)

    def comes(self, term: str) -> None:
        """Forgets what a terminal said before it is come back to, which its replay holds."""
        with self._lock:
            self._left.pop(term, None)
            self._held.pop(term, None)

    def leaves(self, term: str) -> None:
        """Reads a terminal no more: what it says from here on is acknowledged and dropped."""
        with self._lock:
            self._held.pop(term, None)
            if not self._closed:
                self._left[term] = 0

    def ends(self) -> None:
        """Nothing more is coming: whoever reads a terminal is told so."""
        with self._lock:
            self._closed = True
            waiting = list(self._held.values())
            self._left.clear()
        for inbox in waiting:
            inbox.put(None)


class Terminal:
    """One terminal of an environment, viewed by this frontend.

    Iterating it yields what it prints, as bytes, until it ends -- :attr:`status` is then
    its exit status -- or is left. What was read is acknowledged to the host as it goes, so
    a terminal nobody reads waits rather than fills the daemon.
    """

    def __init__(self, ask: _Ask, said: Mapping[str, Any], terms: _Terms) -> None:
        """Made by :meth:`EnvTerminals.open`."""
        self.id = str(said["term"])
        """Its id, which it is come back to by."""
        shell = said.get("shell")
        self.shell: tuple[str, ...] | None = None if shell is None else tuple(shell)
        """The command it runs, None for the login shell of the environment."""
        self.replay = _bytes(said.get("replay"))
        """What it had printed before this frontend came to it; empty for a new one."""
        self.status: int | None = None
        """Its exit status once it has ended, `128 + n` where signal `n` ended it."""
        self._ask = ask
        self._terms = terms
        self._inbox = terms.inbox(self.id)
        self._unacked = 0
        self._over = False
        self._left = False

    def write(self, data: bytes | str) -> None:
        """Types into it; text is typed as UTF-8."""
        self._ask("env.term.input", term=self.id, data=_text(data))

    def resize(self, cols: int, rows: int) -> None:
        """Makes it `cols` columns by `rows` rows."""
        self._ask("env.term.resize", term=self.id, cols=cols, rows=rows)

    def read(self, seconds: float | None = None) -> bytes | None:
        """The next of what it prints.

        Args:
          seconds: How long to wait for it, None for as long as it takes.

        Returns:
          It, or None where nothing came in time, the terminal has ended or it was left.
        """
        while not self._over:
            try:
                message = self._inbox.get(timeout=seconds)
            except queue.Empty:
                return None
            if message is None:
                break
            if message.get("type") == "term_exit":
                status = message.get("status")
                self.status = status if isinstance(status, int) else None
                break
            data = _bytes(message.get("data"))
            self._unacked += len(data)
            if self._unacked >= ACK_EVERY:
                self._acks()
            if data:
                return data
        self._over = True
        return None

    def __iter__(self) -> Iterator[bytes]:
        """Everything it prints from here on, until it ends or is left."""
        while (data := self.read()) is not None:
            yield data

    def _acks(self) -> None:
        """Says what was read. A terminal that has gone refuses it, which loses nothing."""
        acked, self._unacked = self._unacked, 0
        if acked:
            with contextlib.suppress(Exception):
                self._ask("env.term.ack", term=self.id, bytes=acked)

    def leave(self) -> None:
        """Stops reading it and leaves it running, to be come back to by its id."""
        self._left = True
        self._inbox.put(None)
        # What was read and not acknowledged, so the host's count of it starts afresh; what
        # it prints from here on is acknowledged for it, so that it is never held up.
        self._acks()
        if self.status is None:
            self._terms.leaves(self.id)

    def close(self) -> None:
        """Kills it."""
        self.leave()
        self._ask("env.term.close", term=self.id)

    def __enter__(self) -> Self:
        """Views it for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Kills it where it still runs and was not left, however the block ended."""
        if self.status is None and not self._left:
            with contextlib.suppress(Exception):
                self.close()


class EnvTerminals:
    """The terminals of one environment (`env.term.*`)."""

    def __init__(self, ask: _Ask, host: _Ask, terms: _Terms) -> None:
        """Made by :class:`Environment`."""
        self._ask = ask
        self._host = host
        self._terms = terms

    def open(
        self, *, cols: int = 80, rows: int = 24, term: str | None = None
    ) -> Terminal:
        """Starts a terminal in the environment's workdir, or comes back to one.

        Args:
          cols: How many columns it has.
          rows: How many rows.
          term: The id of a terminal of this environment to come back to, which is resized
            and whose :attr:`Terminal.replay` is what it kept; None to start a new one.

        Raises:
          hmz.sdk.Refused: `<role>: this environment has no shell.`, `There is no terminal
            <term>.`, or that terminals are off for paired devices.
        """
        if term is not None:
            self._terms.comes(term)
        said = self._ask("env.term.open", cols=cols, rows=rows, term=term)
        return Terminal(self._host, said, self._terms)

    def list(self) -> builtins.list[Shell]:
        """Every terminal of the environment that is alive, or that a frontend still views."""
        return [
            Shell(
                str(one["term"]),
                str(one["env"]),
                str(one["title"]),
                int(one["cols"]),
                int(one["rows"]),
                bool(one["alive"]),
            )
            for one in self._ask("env.term.list")["terms"]
        ]

    def close(self, term: str) -> None:
        """Kills a terminal by its id, viewed here or not."""
        self._host("env.term.close", term=term)


class Environment:
    """One environment of a host attached to: its files, its git and its terminals."""

    def __init__(self, env: Env, host: _Ask, terms: _Terms) -> None:
        """Made by :meth:`Attached.env`."""
        self.env = env
        """It, as the host described it when this was asked for."""

        def ask(
            method: str,
            /,
            *,
            idem: str | None = None,
            wait: float | None = None,
            **params: Any,
        ) -> Any:
            return host(method, idem=idem, wait=wait, env=env.id, **params)

        self.files = EnvFiles(ask)
        self.git = EnvGit(ask)
        self.terminals = EnvTerminals(ask, host, terms)

    @property
    def id(self) -> str:
        """What the host knows it by."""
        return self.env.id


class Attached:
    """A host attached to as one frontend, for the sake of its environments.

    A context manager: leaving the block lets the host go, which stops nothing there and
    leaves every terminal running.
    """

    def __init__(self, ask: _Ask, said: Mapping[str, Any], heard: Subscription) -> None:
        """Made by :meth:`Envs.attached`."""
        self.sub = str(said["sub"])
        """The epic subscription this is."""
        self.workspace = str(said.get("workspace") or "")
        """The host's workspace, as the daemon names it."""
        self.slot = str(said.get("slot") or "")
        """The host's slot: `""` for the workspace's own, else `chat:<hex>` or `exec:<hex>`."""
        self.gone: str | None = None
        """Why the host let this frontend go, once it has."""
        self._heard = heard
        self._lock = threading.Lock()
        self._envs: list[Env] = []
        self._live = threading.Event()
        self._listed = threading.Event()

        def host(
            method: str,
            /,
            *,
            idem: str | None = None,
            wait: float | None = None,
            **params: Any,
        ) -> Any:
            return ask(method, idem=idem, wait=wait, sub=self.sub, **params)

        self._ask: _Ask = host
        self._detach = ask
        self._terms = _Terms(host)
        threading.Thread(target=self._pumps, daemon=True, name="hmz-envs").start()

    def _pumps(self) -> None:
        """Takes what the host says: how its environments stand, and what its terminals print."""
        for params in self._heard:
            message = params.get("message")
            if not isinstance(message, dict):
                continue
            kind = message.get("type")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if kind == "envs":
                held = [_env(one) for one in message.get("envs") or ()]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportUnknownArgumentType]
                with self._lock:
                    self._envs = held
                # A host lists its environments a moment after its epic opens them.
                if held:
                    self._listed.set()
                else:
                    self._listed.clear()
            elif kind == "live":
                self._live.set()
            elif kind in ("term", "term_exit"):
                self._terms.told(message)  # pyright: ignore[reportUnknownArgumentType]
            elif kind == "gone":
                self.gone = str(message.get("why") or "")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                break
        # Nothing more is coming: nobody is left waiting on it.
        self._terms.ends()
        self._live.set()
        self._listed.set()

    def live(self, seconds: float | None = _PATIENCE) -> bool:
        """Waits for the host to have said how it stands, and says whether it has."""
        return self._live.wait(seconds) and self.gone is None

    def envs(self, wait: float = 0) -> list[Env]:
        """The host's environments, as it last said they stand.

        One per environment of the epic or chat going there, or of the last one: each root
        environment in the order of its roles, each derived one after the one it came from.

        Args:
          wait: How many seconds to wait for the host to list one where it lists none: an
            epic just started has opened none yet.
        """
        if wait:
            self._listed.wait(wait)
        with self._lock:
            return list(self._envs)

    def env(self, name: str | None = None) -> Environment:
        """One environment of the host.

        Args:
          name: Its `id`, its `chain` or its `role`, tried in that order; None for the first
            that is available and open, else the first.

        Raises:
          hmz.sdk.Refused: `There is no environment <name>.`, or `No environment is open
            here yet.` where the host has none.
        """
        held = self.envs()
        found: Env | None = None
        if name is None:
            ready = [one for one in held if one.available and one.open]
            found = next(iter(ready or held), None)
        else:
            for by in ("id", "chain", "role"):
                found = next((one for one in held if getattr(one, by) == name), None)
                if found is not None:
                    break
        if found is None:
            if name is None:
                raise _refused("No environment is open here yet.", 404)
            raise _refused(f"There is no environment {name}.", 404)
        return Environment(found, self._ask, self._terms)

    def close(self) -> None:
        """Lets the host go. Its epic, its chat and its terminals go on."""
        # Let go of first, and heard until then: what a host says to a subscription nobody
        # hears is kept for whoever takes it up, which nobody will.
        with contextlib.suppress(Exception):
            self._detach("epic.detach", sub=self.sub)
        self._heard.close()

    def __enter__(self) -> Self:
        """Stays attached for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Lets the host go, however the block ended."""
        self.close()


class Envs(Family):
    """A host's environments: files, terminals and git."""

    METHODS: ClassVar = (
        "hosts.env.list",
        "hosts.env.read",
        "hosts.env.write",
        "hosts.env.exec",
        "hosts.env.grep",
        "env.list",
        "env.stat",
        "env.read",
        "env.find",
        "env.search",
        "env.write",
        "env.mkdir",
        "env.rename",
        "env.remove",
        "env.term.open",
        "env.term.input",
        "env.term.resize",
        "env.term.ack",
        "env.term.close",
        "env.term.list",
        "env.git.status",
        "env.git.diff",
        "env.git.log",
        "env.git.stage",
        "env.git.unstage",
        "env.git.discard",
        "env.git.commit",
        "env.git.snapshots",
        "env.git.rewind",
    )

    def list(self, workspace: str, *, slot: str | None = None) -> list[Role]:
        """The envs of the epic going on a host, one per env role of its flow.

        Args:
          workspace: The host's workspace, an absolute path of the daemon's machine.
          slot: The host's slot, None for the workspace's own host.

        Raises:
          hmz.sdk.Refused: `no flow is running, so no env is open`, or that no host holds
            that workspace and slot.
        """
        said = self._call("hosts.env.list", workspace=workspace, slot=slot)
        return [
            Role(
                str(one["name"]),
                str(one["kind"]),
                str(one["workdir"]),
                tuple(one["can"]),
            )
            for one in said["envs"]
        ]

    def read(
        self,
        workspace: str,
        env: str,
        path: str,
        *,
        slot: str | None = None,
        offset: int | None = None,
        length: int | None = None,
    ) -> Text:
        """Reads a file of an env as text, as the epic's flow would.

        Args:
          workspace: The host's workspace.
          env: The env's role.
          path: The file, relative to the env's workdir, which it may not leave.
          slot: The host's slot, None for the workspace's own host.
          offset: The byte to read from, None for the first.
          length: How many bytes to read, None for at most 1048576.
        """
        said = self._call(
            "hosts.env.read",
            workspace=workspace,
            slot=slot,
            env=env,
            path=path,
            offset=offset,
            length=length,
        )
        return Text(str(said["text"]), int(said["size"]), bool(said["eof"]))

    def write(
        self,
        workspace: str,
        env: str,
        path: str,
        text: str,
        *,
        slot: str | None = None,
        idem: str | None = None,
    ) -> int:
        """Writes text as the whole of a file of an env, making the directories it lies in.

        Returns:
          How many bytes were written.
        """
        said = self._call(
            "hosts.env.write",
            workspace=workspace,
            slot=slot,
            env=env,
            path=path,
            text=text,
            idem=idem,
        )
        return int(said["size"])

    def exec(
        self,
        workspace: str,
        env: str,
        argv: Sequence[str],
        *,
        slot: str | None = None,
        seconds: int | None = None,
        idem: str | None = None,
        wait: float | None = None,
    ) -> Ran:
        """Runs a command in an env's workdir, and waits for it.

        Args:
          workspace: The host's workspace.
          env: The env's role.
          argv: The command and its arguments.
          slot: The host's slot, None for the workspace's own host.
          seconds: How long it may run before it is killed, 1 to 3600; None for 120.
          idem: The key this is done once under.
          wait: How long the answer is waited for, None for as long as it takes.
        """
        said = self._call(
            "hosts.env.exec",
            workspace=workspace,
            slot=slot,
            env=env,
            argv=[*argv],
            seconds=seconds,
            idem=idem,
            wait=wait,
        )
        return Ran(said.get("code"), str(said["stdout"]), str(said["stderr"]))

    def grep(
        self,
        workspace: str,
        env: str,
        pattern: str,
        *,
        slot: str | None = None,
        path: str | None = None,
        limit: int | None = None,
    ) -> Grepped:
        """Searches the files of an env for a POSIX extended regular expression.

        Args:
          workspace: The host's workspace.
          env: The env's role.
          pattern: The expression.
          slot: The host's slot, None for the workspace's own host.
          path: Where to search under, None for the whole workdir.
          limit: The most matches answered, 1 to 2000; None for 200.
        """
        said = self._call(
            "hosts.env.grep",
            workspace=workspace,
            slot=slot,
            env=env,
            pattern=pattern,
            path=path,
            limit=limit,
        )
        return Grepped(
            tuple(
                Line(str(one["path"]), int(one["line"]), str(one["text"]))
                for one in said["matches"]
            ),
            bool(said["more"]),
        )

    def host(self, chat: str) -> tuple[str, str]:
        """The host a chat is going on, as its workspace and its slot.

        Args:
          chat: The chat's id.

        Raises:
          hmz.sdk.Refused: `There is no chat <id>.`, or `This chat has folded away.` for
            one no host holds.
        """
        held = self._call("chat.get", chat=chat)
        workspace, slot = str(held.get("workspace") or ""), str(held.get("slot") or "")
        if not slot:
            raise _refused("This chat has folded away.", 409)
        return workspace, slot

    def attached(
        self,
        workspace: str | None = None,
        *,
        slot: str | None = None,
        chat: str | None = None,
        start: bool = False,
        wait: float | None = _PATIENCE,
    ) -> Attached:
        """Attaches to a host as one frontend, to work in its environments.

        Args:
          workspace: The host's workspace, an absolute path of the daemon's machine.
          slot: The host's slot, None for the workspace's own host.
          chat: A chat's id, in place of both: the host is the one the chat is going on.
          start: Whether to start the workspace's own host where none is held, as attaching
            does of itself; a host just started has no environment, so by default one that
            is not held is refused instead.
          wait: How long the host is given to say how its environments stand.

        Returns:
          The host, attached to; closing it, or leaving its `with` block, lets it go.

        Raises:
          hmz.sdk.Refused: `no runs are held in <workspace>` where no host is, `This chat
            has folded away.` for a chat that is not going, and whatever `epic.attach`
            refuses.
          TimeoutError: If the host did not say how it stands within `wait`.
        """
        if chat is not None:
            workspace, slot = self.host(chat)
        elif not start:
            self._call("hosts.status", workspace=workspace, slot=slot)
        # Before the call: a host speaks as soon as it is attached to.
        self._listens()
        said = self._call("epic.attach", workspace=workspace, slot=slot, replay=False)
        host = Attached(self._call, said, self._heard("epic.event", str(said["sub"])))
        if not host.live(wait):
            gone = host.gone
            host.close()
            if gone is not None:
                raise _refused(gone or "this host has closed", 409)
            raise TimeoutError(f"the host did not answer in {wait}s")
        return host
