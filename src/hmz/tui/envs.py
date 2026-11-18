"""`/env`: what each environment of the epic or chat in front of you can do, from here.

Every environment a run uses -- a role's workspace, one derived from it, a chat's own -- is
listed by the host in its `envs` snapshot, with the capabilities its driver really has. Each
of those is a panel here: its files, browsed and edited in a code editor that saves itself;
its git changes, grouped as a source-control view groups them, staged and committed from the
list; its snapshots, rewound to; and a shell in it, which is this terminal handed over to a
terminal in the environment until `~.` or the shell ending hands it back.

What is said to the host is the `env.*` methods, made through the interface's own link with
the epic's subscription: the same session the rest of the epic is reached through, so that a
terminal's output -- which reaches only the frontend that opened it -- comes back here.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import difflib
import os
import posixpath
import queue
import select
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from rich.markup import escape
from rich.syntax import Syntax
from textual import on
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from .pick import Action, Form, Key, Popup, Question, Sheet, handed_over

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual.app import App, ComposeResult
    from textual.timer import Timer

__all__ = [
    "ACK_EVERY",
    "CHUNK",
    "LARGE",
    "PANELS",
    "Changes",
    "Commit",
    "Conflict",
    "Credit",
    "Desk",
    "Diff",
    "Editing",
    "Envs",
    "Escape",
    "Files",
    "Inbox",
    "Matches",
    "Named",
    "Opens",
    "Reach",
    "Read",
    "Snapshots",
    "Sure",
    "about",
    "bridge",
    "default_panel",
    "grouped",
    "language_of",
    "opens_env",
    "opens_page",
    "panels_of",
    "tree",
    "unified",
    "used",
]

#: Each page an environment can have, in the order `tab` steps through them, and the
#: capabilities of which any one gives it: what the driver can really do, whatever the flow
#: declared.
PANELS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("files", "Files", ("files",)),
    ("changes", "Changes", ("git", "git_worktree")),
    ("shell", "Shell", ("shell",)),
    ("snapshots", "Snapshots", ("rewind",)),
)

#: How much of a file one `env.read` asks for, which is the most the host gives at once.
CHUNK = 1024 * 1024

#: How large a file is still edited here; a larger one is not opened in the editor.
LARGE = 5 * 1024 * 1024

#: How much terminal output is written out before it is acknowledged, so the host sends more.
ACK_EVERY = 64 * 1024

#: How long the editor waits after the last edit before it saves, in seconds.
_IDLE = 1.0

#: What a refusal of a write says, ending, where the file changed since it was read.
_CHANGED = "changed since you read it."

#: The dot the parts of a line are separated by.
_DOT = " · "

#: What the ids of the headings of a list are put under: a byte no path has.
_HEADING = "\x1e"

#: What separates a group from a path in the id of a row of the changes.
_SEP = "\x1f"

#: The extensions, and the whole names, each language the editor colours is known by.
_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".sql": "sql",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".svg": "xml",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
}
_NAMED = {".bashrc": "bash", ".zshrc": "bash", ".profile": "bash", "uv.lock": "toml"}


def panels_of(env: Mapping[str, Any]) -> list[str]:
    """The panels one environment has, in order, as its capabilities give them.

    Args:
      env: The environment, as the `envs` snapshot describes it.

    Returns:
      Each page's name: `files`, `changes`, `shell` and `snapshots`, those it has.
    """
    caps = set(env.get("caps") or ())
    return [name for name, _, gates in PANELS if caps.intersection(gates)]


def default_panel(env: Mapping[str, Any]) -> str:
    """The panel one environment opens on: the first whose capability the flow declared.

    Args:
      env: The environment, as the `envs` snapshot describes it.

    Returns:
      That panel's name, or `files` where the flow declared none of them.
    """
    declared = set(env.get("declared") or ())
    has = set(panels_of(env))
    for name, _, gates in PANELS:
        if name in has and declared.intersection(gates):
            return name
    return "files"


def tree(envs: Sequence[Mapping[str, Any]]) -> list[tuple[int, Mapping[str, Any]]]:
    """The environments as a tree: by role, each derived one under the one it came from.

    Args:
      envs: The environments, as the `envs` snapshot lists them.

    Returns:
      Each environment and how deep it is, in the order to list them: the roles as they
      first appear, and under each environment the ones derived from it.
    """
    ids = {str(one.get("id")) for one in envs}
    under: dict[str, list[Mapping[str, Any]]] = {}
    roots: dict[str, list[Mapping[str, Any]]] = {}
    for one in envs:
        parent = one.get("parent")
        if parent is not None and str(parent) in ids:
            under.setdefault(str(parent), []).append(one)
        else:
            roots.setdefault(str(one.get("role") or ""), []).append(one)
    laid: list[tuple[int, Mapping[str, Any]]] = []

    def lays(one: Mapping[str, Any], depth: int) -> None:
        laid.append((depth, one))
        for child in under.get(str(one.get("id")), []):
            lays(child, depth + 1)

    for group in roots.values():
        for one in group:
            lays(one, 0)
    return laid


def language_of(path: str, available: Sequence[str] = ()) -> str | None:
    """The language the editor colours a file as, by its name.

    Args:
      path: The file.
      available: The languages the editor has, or empty for any it could have.

    Returns:
      The language, or None for a file it has none for.
    """
    name = posixpath.basename(path)
    found = _NAMED.get(name) or _LANGUAGES.get(posixpath.splitext(name)[1].lower())
    if found is None or (available and found not in available):
        return None
    return found


def unified(old: bytes | None, new: bytes | None, path: str) -> str:
    """One file's change, as a unified diff of what it was and what it is.

    Args:
      old: What it was, or None where it was not there.
      new: What it is, or None where it is gone.
      path: The file, as the diff names it.

    Returns:
      The diff, "" where the two are the same.
    """

    def lines(data: bytes | None) -> list[str]:
        if data is None:
            return []
        said = data.decode("utf-8", "replace").splitlines(keepends=True)
        if said and not said[-1].endswith("\n"):
            said[-1] += "\n"
        return said

    return "".join(
        difflib.unified_diff(
            lines(old),
            lines(new),
            "/dev/null" if old is None else f"a/{path}",
            "/dev/null" if new is None else f"b/{path}",
        )
    )


#: The groups the changes are listed in, in order.
_CONFLICTS, _STAGED = "Merge Changes", "Staged Changes"
_GROUPS = (_CONFLICTS, _STAGED, "Changes", "Untracked")


def grouped(
    files: Sequence[Mapping[str, Any]],
) -> list[tuple[str, list[Mapping[str, Any]]]]:
    """The changed files as a source-control view groups them.

    A file changed in the index and again in the worktree is in both staged and not, as
    it is in a source-control view: the two are two different diffs.

    Args:
      files: The files `env.git.status` lists.

    Returns:
      Each group that has any -- Merge Changes (the conflicts), Staged Changes, Changes,
      Untracked -- and its files.
    """
    groups: dict[str, list[Mapping[str, Any]]] = {name: [] for name in _GROUPS}
    for one in files:
        state = one.get("state")
        if state == "conflict":
            groups[_CONFLICTS].append(one)
        elif state == "untracked":
            groups["Untracked"].append(one)
        else:
            if str(one.get("index") or ".") not in ".?":
                groups[_STAGED].append(one)
            if str(one.get("worktree") or ".") not in ".?":
                groups["Changes"].append(one)
    return [(name, held) for name, held in groups.items() if held]


def used(record: Mapping[str, Any], envs: Sequence[Mapping[str, Any]] = ()) -> str:
    """One `env_used` record, as the dim line the transcript draws it as.

    Args:
      record: The record.
      envs: The environments, which the one used is named by its role among.

    Returns:
      The line: who did what, to what, where.
    """
    env = str(record.get("env") or "")
    named = next(
        (
            str(one.get("chain") or one.get("role"))
            for one in envs
            if one.get("id") == env
        ),
        env,
    )
    path = str(record.get("path") or "")
    by = str(record.get("by") or "somebody")
    return f"{by} {record.get('what') or 'used'}{f' {path}' if path else ''} in {named}"


#: A kibibyte.
_KIB = 1024


def _sized(size: int) -> str:
    """A size, as a listing of files says it."""
    if size < _KIB:
        return f"{size} B"
    amount, unit = float(size) / _KIB, "KiB"
    for larger in ("MiB", "GiB"):
        if amount < _KIB:
            break
        amount, unit = amount / _KIB, larger
    return f"{amount:.1f} {unit}"


def _encoded(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decoded(said: object) -> bytes:
    return base64.b64decode(str(said or ""))


def _conflicted(why: BaseException) -> bool:
    """Whether a refused write was refused because the file changed since it was read."""
    return str(why).endswith(_CHANGED)


# -- Reaching the host ------------------------------------------------------------------------


class Escape:
    """The `~.` that leaves a shell, as ssh's: a tilde first on a line, then a dot.

    A tilde first on a line is held until the next key says what it was: a dot leaves, a
    second tilde is one tilde sent, and anything else is the tilde and that key sent both.
    """

    def __init__(self) -> None:
        self._first = True
        self._held = False

    def typed(self, data: bytes) -> tuple[bytes, bool]:
        """Takes what was typed.

        Args:
          data: The bytes, as the terminal gave them.

        Returns:
          What to send on, and whether to leave -- in which case nothing after the dot is.
        """
        out = bytearray()
        for byte in data:
            key = bytes([byte])
            if self._held:
                self._held = False
                if key == b".":
                    return bytes(out), True
                out += b"~"
                if key == b"~":
                    self._first = False
                    continue
            if key == b"~" and self._first:
                self._held = True
                continue
            out += key
            self._first = key in (b"\r", b"\n")
        return bytes(out), False


class Credit:
    """How much terminal output has been written out since it was last acknowledged."""

    def __init__(self, every: int = ACK_EVERY) -> None:
        self._every = every
        self._unacked = 0

    def took(self, size: int) -> int:
        """Counts bytes written out.

        Args:
          size: How many.

        Returns:
          How many to acknowledge now, or 0 until there are enough to.
        """
        self._unacked += size
        if self._unacked < self._every:
            return 0
        return self.rest()

    def rest(self) -> int:
        """What is written out and not acknowledged yet, counted as acknowledged from here."""
        acked, self._unacked = self._unacked, 0
        return acked


class Inbox:
    """Where a shell being bridged is handed its terminal's messages, from any thread.

    A queue, and a pipe a byte is written down per message, so that the bridge waits on its
    keyboard and on its terminal in one `select`.
    """

    def __init__(self, term: str) -> None:
        #: The terminal, or "" while it is being opened, which takes any terminal's messages.
        self.term = term
        self._queue: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        self._read, self._write = os.pipe()
        os.set_blocking(self._read, False)
        os.set_blocking(self._write, False)

    def fileno(self) -> int:
        """The end `select` waits on."""
        return self._read

    def put(self, message: dict[str, Any]) -> None:
        """Hands one message on, waking the bridge."""
        self._queue.put(message)
        self.wake()

    def wake(self) -> None:
        """Wakes the bridge, with or without a message for it."""
        with contextlib.suppress(OSError):
            os.write(self._write, b"\0")

    def taken(self) -> list[dict[str, Any]]:
        """Every message waiting, oldest first, and the bytes that woke the bridge for them."""
        with contextlib.suppress(OSError):
            while os.read(self._read, 4096):
                pass
        took: list[dict[str, Any]] = []
        with contextlib.suppress(queue.Empty):
            while True:
                took.append(self._queue.get_nowait())
        return took

    def close(self) -> None:
        """Lets go of the pipe."""
        for one in (self._read, self._write):
            with contextlib.suppress(OSError):
                os.close(one)


class Reach:
    """The host, as the panels reach it: its methods, its environments, and their terminals.

    Held by the interface for as long as it runs, across the hosts it moves between: what it
    asks is asked of whichever host the interface is attached to then.
    """

    def __init__(
        self,
        ask: Callable[[dict[str, Any]], dict[str, Any]],
        envs: Callable[[], Sequence[Mapping[str, Any]]],
        say: Callable[[str, str], object] = lambda _text, _style: None,
    ) -> None:
        """Holds how to reach the host.

        Args:
          ask: What asks the host one thing, `do` and what it takes, and answers or raises
            the refusal.
          envs: The environments as the host last said they stand.
          say: What puts a line on the interface's transcript, in a style.
        """
        self._ask = ask
        self._envs = envs
        self.say = say
        self._watchers: list[Callable[[], None]] = []
        self._bridged: Inbox | None = None
        self._credits: dict[str, Credit] = {}
        self._lock = threading.Lock()

    def ask(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        """Asks the host one `env.*` method, and waits for the answer.

        Args:
          method: The method.
          params: What it takes, less the subscription, which the link adds.

        Returns:
          The answer.
        """
        return self._ask({"do": method, **params})

    def envs(self) -> list[Mapping[str, Any]]:
        """The environments, as the host last said they stand."""
        return list(self._envs())

    def watching(self, watcher: Callable[[], None]) -> Callable[[], None]:
        """Calls `watcher` whenever an environment may have changed, until told not to.

        Args:
          watcher: What to call, on the interface's own thread.

        Returns:
          What stops it being called.
        """
        self._watchers.append(watcher)
        return lambda: (
            self._watchers.remove(watcher) if watcher in self._watchers else None
        )

    def moved(self) -> None:
        """Says an environment may have changed: one was used, or a turn ended."""
        for one in list(self._watchers):
            one()

    def bridging(self, inbox: Inbox | None) -> None:
        """Hands the messages of one terminal to a shell being bridged, or to nobody.

        Args:
          inbox: Where to hand them, or None once the bridge is over.
        """
        with self._lock:
            self._bridged = inbox

    def told(self, message: Mapping[str, Any]) -> bool:
        """Takes a terminal's message, which is the bridge's or, while there is none, nobody's.

        A terminal left running is still one this frontend watches, and the host stops it
        once its output goes unacknowledged; so what nobody is reading is acknowledged here.

        Args:
          message: What the host told this frontend.

        Returns:
          Whether it was a terminal's, taken here rather than drawn.
        """
        kind = message.get("type")
        if kind not in ("term", "term_exit"):
            return False
        term = str(message.get("term") or "")
        with self._lock:
            bridged = self._bridged
        if bridged is not None and bridged.term in (term, ""):
            bridged.put(dict(message))
            return True
        if kind == "term_exit":
            self._credits.pop(term, None)
            return True
        acked = self._credits.setdefault(term, Credit()).took(
            len(_decoded(message.get("data")))
        )
        if acked:
            threading.Thread(
                target=self._acks, args=(term, acked), daemon=True, name="hmz-env-ack"
            ).start()
        return True

    def _acks(self, term: str, acked: int) -> None:
        with contextlib.suppress(Exception):
            self.ask("env.term.ack", {"term": term, "bytes": acked})


@dataclass
class Desk:
    """One environment, as the panels work on it: what the host said of it, and how to ask.

    Attributes:
      env: The environment, as the `envs` snapshot describes it.
      reach: The host.
    """

    env: Mapping[str, Any]
    reach: Reach

    @property
    def id(self) -> str:
        """What the host knows it by."""
        return str(self.env.get("id") or "")

    @property
    def named(self) -> str:
        """What it is called: its chain of roles, or its role."""
        return str(self.env.get("chain") or self.env.get("role") or self.id)

    @property
    def workdir(self) -> str:
        """Where it works."""
        return str(self.env.get("workdir") or "")

    def ask(self, method: str, /, **params: Any) -> dict[str, Any]:
        """Asks the host one method about this environment, and waits for the answer.

        Args:
          method: The method.
          params: What it takes besides the environment.

        Returns:
          The answer.
        """
        return self.reach.ask(method, {"env": self.id, **params})

    async def asks(self, method: str, /, **params: Any) -> dict[str, Any]:
        """:meth:`ask`, off the interface's thread."""
        return await asyncio.to_thread(self.ask, method, **params)


class Read(NamedTuple):
    """A file as it was read.

    Attributes:
      data: What it holds, as far as it was read.
      etag: What it was when read, which a write is made against.
      size: How large it is.
      whole: Whether all of it was read.
    """

    data: bytes
    etag: str
    size: int
    whole: bool


async def _read(desk: Desk, path: str, cap: int = LARGE) -> Read:
    """Reads a file, a chunk at a time, up to `cap`; again where it changed while being read."""
    for _ in range(3):
        chunks: list[bytes] = []
        offset, etag, size, whole, moved = 0, "", 0, False, False
        while True:
            said = await desk.asks("env.read", path=path, offset=offset, length=CHUNK)
            data = _decoded(said.get("data"))
            if etag and said.get("etag") != etag:
                moved = True
                break
            etag, size = str(said.get("etag") or ""), int(said.get("size") or 0)
            chunks.append(data)
            offset += len(data)
            if said.get("eof") or not data:
                whole = True
                break
            if offset >= cap:
                break
        if not moved:
            return Read(b"".join(chunks), etag, size, whole)
    raise OSError(f"{path} kept changing while it was read")


# -- The shell ----------------------------------------------------------------------------------


def bridge(
    ask: Callable[[str, Mapping[str, Any]], object],
    inbox: Inbox,
    *,
    stdin: int,
    stdout: int,
    size: Callable[[], tuple[int, int]] | None = None,
    replay: bytes = b"",
) -> str:
    """Bridges this terminal to one in an environment, until it ends or is left.

    What is typed goes to the terminal as it is typed, but for `~.` after a newline, which
    leaves it running; what it writes is written out, and acknowledged every
    :data:`ACK_EVERY` bytes. The terminal is put in raw mode for as long, where it is one,
    and told of every change of size.

    Args:
      ask: What asks the host one method, and raises its refusal.
      inbox: Where the terminal's messages arrive.
      stdin: What is typed.
      stdout: What is written to.
      size: The terminal's size, as columns and rows, or None not to follow it.
      replay: What the terminal wrote before this frontend came to it.

    Returns:
      How it ended: its exit status, or that it was left running.
    """
    term = inbox.term
    escape_ = Escape()
    credit = Credit()
    resized = threading.Event()
    _written(stdout, replay)
    restore = _raw(stdin)
    previous: Any = None
    if size is not None and threading.current_thread() is threading.main_thread():

        def winched(_signal: int, _frame: object) -> None:
            resized.set()
            inbox.wake()

        previous = signal.signal(signal.SIGWINCH, winched)
    try:
        while True:
            ready, _, _ = select.select([stdin, inbox], [], [])
            if resized.is_set() and size is not None:
                resized.clear()
                cols, rows = size()
                ask("env.term.resize", {"term": term, "cols": cols, "rows": rows})
            if inbox in ready:
                for message in inbox.taken():
                    if message.get("term") != term:
                        continue  # another terminal's, told while this one was opening
                    kind = message.get("type")
                    if kind == "term_exit":
                        return f"exited with status {message.get('status')}"
                    if kind != "term":
                        continue
                    data = _decoded(message.get("data"))
                    _written(stdout, data)
                    if acked := credit.took(len(data)):
                        ask("env.term.ack", {"term": term, "bytes": acked})
            if stdin in ready:
                typed = os.read(stdin, 4096)
                if not typed:
                    return "left; it keeps running"
                sent, leaves = escape_.typed(typed)
                if sent:
                    ask("env.term.input", {"term": term, "data": _encoded(sent)})
                if leaves:
                    return "left; it keeps running"
    except Exception as why:  # noqa: BLE001 -- the terminal or the host gone, said
        return f"ended: {why}"
    finally:
        restore()
        if previous is not None:
            signal.signal(signal.SIGWINCH, previous)
        # What was written and not yet acknowledged, so the host's count of it starts afresh.
        if rest := credit.rest():
            with contextlib.suppress(Exception):
                ask("env.term.ack", {"term": term, "bytes": rest})


def _written(fd: int, data: bytes) -> None:
    """Writes all of `data`, however much each write takes."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def _raw(fd: int) -> Callable[[], None]:
    """Puts a terminal in raw mode, answering what puts it back; nothing for one that is not."""
    if not os.isatty(fd):
        return lambda: None
    import termios
    import tty

    was = termios.tcgetattr(fd)
    tty.setraw(fd)
    return lambda: termios.tcsetattr(fd, termios.TCSADRAIN, was)


def _size() -> tuple[int, int]:
    """This terminal's size, as columns and rows."""
    try:
        size = os.get_terminal_size(sys.__stdout__.fileno() if sys.__stdout__ else 1)
    except (OSError, ValueError):
        return 80, 24
    return size.columns, size.lines


async def _shell(host: App[Any], desk: Desk, term: str = "") -> None:
    """Opens a shell in an environment, or comes back to one, and hands it this terminal.

    Args:
      host: The interface, which hands the terminal over.
      desk: The environment.
      term: The terminal to come back to, or "" for a new one.
    """
    say = desk.reach.say
    stdin, stdout = sys.__stdin__, sys.__stdout__
    if (
        host.is_headless
        or stdin is None
        or stdout is None
        or not (stdin.isatty() and stdout.isatty())
    ):
        say(f"hmz: a shell in {desk.named} needs this to be a terminal", "red")
        return
    cols, rows = _size()
    # Taking whatever a terminal says from before it is open: a new shell's prompt is told
    # as soon as it starts, which may be before the answer saying which terminal it is.
    inbox = Inbox(term)
    desk.reach.bridging(inbox)
    try:
        opened = await desk.asks(
            "env.term.open", cols=cols, rows=rows, **({"term": term} if term else {})
        )
    except Exception as why:  # noqa: BLE001 -- refused, in the host's words
        desk.reach.bridging(None)
        inbox.close()
        say(f"hmz: {why}", "red")
        return
    inbox.term = str(opened.get("term") or term)
    try:
        with handed_over(cast("App[None]", host)):
            ended = bridge(
                desk.reach.ask,
                inbox,
                stdin=stdin.fileno(),
                stdout=stdout.fileno(),
                size=_size,
                replay=_decoded(opened.get("replay")),
            )
    finally:
        desk.reach.bridging(None)
        inbox.close()
    # A refusal of what was typed -- a paired device's, among them -- said as one.
    say(
        f"shell in {desk.named}: {ended}", "red" if ended.startswith("ended") else "dim"
    )


# -- Sheets -------------------------------------------------------------------------------------


@dataclass
class _Row:
    """One row of a list: what it answers with, what it is called, and the line about it."""

    id: str
    label: str
    about: str = ""
    muted: bool = False
    heading: bool = False


#: The most rows a list draws: one of every file of a large repository is a list to narrow.
_SHOWN = 400


class _Listing(Sheet[str]):
    """A list of rows this module's sheets draw alike, with headings, read off the host."""

    #: The question across the top, and the line under it.
    asked = ""
    about = ""
    #: Whether the list is searched, which gives it the button and `/`.
    SEARCHES: ClassVar[bool] = True
    #: Whether the row the list opened on is ticked as the one in force.
    TICKS: ClassVar[bool] = True
    #: Whether the rows are read off the host once it has opened, rather than given.
    READS: ClassVar[bool] = False

    def __init__(self) -> None:
        super().__init__()
        self._rows_now: list[_Row] = []
        #: Whether the rows have been read, for a list read off the host as it opens.
        self._read_in = not self.READS
        self._current = ""
        #: What went wrong last, said under the list until something else is.
        self._said = ""

    def listed(self) -> list[_Row]:
        """The rows, as this sheet last read them."""
        return self._rows_now

    def keys(self) -> list[Key]:
        """This sheet's keys for its list, in the order they are reached for."""
        return [Key("enter", "open"), Key("esc", "back")]

    def actions(self) -> list[Action]:
        """Searching, for a list that is searched."""
        return [self._searches()] if self.SEARCHES else []

    def _ask(self) -> None:
        self.query_one("#asked", Label).update(escape(self.asked))
        self.query_one("#about", Label).update(escape(self.about))
        self._fill()

    def shows(self, rows: list[_Row], said: str = "") -> None:
        """Puts new rows up, and what to say under them."""
        self._rows_now, self._said = rows, said
        self._read_in = True
        if self.is_mounted:
            self._ask()
            if not isinstance(self.focused, Input):
                self._settles_focus()

    def _settles_focus(self) -> None:
        """Puts the focus on the list while it is still being read, as on one that has rows.

        A list read off the host is empty for a moment as it opens, and the bar the focus
        would land on then is not where it should be once the rows arrive.
        """
        listing = self.query_one("#choices", OptionList)
        if not self._read_in and listing.display:
            listing.focus()
            return
        super()._settles_focus()

    def _fill(self) -> None:
        listing = self.query_one("#choices", OptionList)
        rows = [
            one
            for one in self.listed()
            if one.heading or self.fits(one.label, one.about)
        ]
        if self._typed:
            rows = sorted(
                (one for one in rows if not one.heading),
                key=lambda one: self.ranks(one.label, one.about),
            )
        rows = rows[:_SHOWN]
        ids = [one.id for one in rows if not one.heading]
        sought = self._sought(ids)
        was = (
            (self.under() if sought is None else sought)
            if listing.option_count
            else None
        )
        landing = (
            was
            if was in ids
            else self._current
            if self._current in ids
            else ids[0]
            if ids
            else ""
        )
        options: list[Option] = []
        for at, one in enumerate(rows):
            if one.heading:
                options.append(
                    Option(
                        f"[b $accent]{escape(one.label)}[/]",
                        id=f"{_HEADING}{at}",
                        disabled=True,
                    )
                )
            elif one.muted:
                options.append(
                    Option(
                        f" [$text-muted]{escape(one.label)}  {escape(one.about)}[/]",
                        id=f"={one.id}",
                    )
                )
            else:
                options.append(
                    Option(
                        self._row(
                            at,
                            one.label,
                            one.about,
                            here=one.id == landing,
                            inforce=self.TICKS
                            and bool(self._current)
                            and one.id == self._current,
                        ),
                        id=f"={one.id}",
                    )
                )
        listing.set_options(options)
        at = next(
            (
                at
                for at, one in enumerate(rows)
                if not one.heading and one.id == landing
            ),
            None,
        )
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._said)}[/]" if self._said else self.nothing()
        )
        self._footed(*self.keys())

    def nothing(self) -> str:
        """What to say under the list while nothing went wrong, as markup."""
        return ""

    def under(self) -> str:
        """The row under the cursor, "" on a heading."""
        said = super().under()
        return "" if said.startswith(_HEADING) else said

    @on(OptionList.OptionSelected)
    def _picked(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        picked = str(event.option.id or "").removeprefix("=")
        if picked and not picked.startswith(_HEADING):
            self.chosen(picked)

    def chosen(self, row: str) -> None:
        """Takes a row picked, which answers the sheet unless a sheet says otherwise.

        Args:
          row: The row, by id.
        """
        self.dismiss(row)

    def fails(self, why: BaseException | str) -> None:
        """Says what went wrong, under the list."""
        self._said = str(why)
        if self.is_mounted:
            self._fill()

    def typing(self) -> bool:
        """Whether the keys are going to the search box, where a letter is a letter."""
        return (
            self._searching and self.focused is not None and self.focused.id == "seek"
        )


class Envs(_Listing):
    """The environments of the epic or chat in front of you, by role: each one's panels."""

    asked = "Environments"

    def __init__(self, reach: Reach, host: App[Any]) -> None:
        """Lists the environments.

        Args:
          reach: The host, which says what they are.
          host: The interface, which a shell hands its terminal over from.
        """
        super().__init__()
        self._reach = reach
        self._host = host
        self._stops: Callable[[], None] = lambda: None
        self.about = "Every environment the run in front of you uses."
        self._rows_now = self._rows()

    def _rows(self) -> list[_Row]:
        rows: list[_Row] = []
        for depth, one in tree(self._reach.envs()):
            chain = str(one.get("chain") or one.get("role") or one.get("id"))
            label = ("  " * (depth - 1) + "└ " if depth else "") + chain
            closed = not one.get("open", True)
            rows.append(_Row(str(one.get("id")), label, about(one), muted=closed))
        return rows

    def crumb(self) -> str:
        return "Environments"

    def on_mount(self) -> None:
        self._stops = self._reach.watching(lambda: self.shows(self._rows(), self._said))

    def on_unmount(self) -> None:
        self._stops()

    def nothing(self) -> str:
        return "" if self._rows_now else "[$text-muted]no environment is open here[/]"

    def chosen(self, row: str) -> None:
        env = next((one for one in self._reach.envs() if one.get("id") == row), None)
        if env is not None:
            desk = Desk(env, self._reach)
            opens_page(self._host, desk, default_panel(env))


def about(env: Mapping[str, Any]) -> str:
    """What one environment is, in a line: backend, provider, workdir, facts, and closed."""
    facts = cast("dict[str, Any]", env.get("facts") or {})
    sized = [
        f"{facts[key]} {what}"
        for key, what in (("cpu", "CPUs"), ("memory", "memory"), ("gpu_count", "GPUs"))
        if facts.get(key)
    ]
    return _DOT.join(
        str(one)
        for one in (
            env.get("backend"),
            env.get("provider"),
            env.get("workdir"),
            *sized,
            *(() if env.get("open", True) else ("closed",)),
        )
        if one
    )


def opens_page(host: App[Any], desk: Desk, page: str) -> None:
    """Opens one page of an environment: a sheet, or the shell, which takes the terminal.

    Args:
      host: The interface.
      desk: The environment.
      page: `files`, `changes`, `shell` or `snapshots`.
    """
    if page == "shell":
        host.run_worker(_shells(host, desk), group="shell", exclusive=True)
    elif page == "changes":
        host.push_screen(Changes(desk, host))
    elif page == "snapshots":
        host.push_screen(Snapshots(desk, host))
    else:
        host.push_screen(Files(desk, host))


async def _shells(host: App[Any], desk: Desk) -> None:
    """Comes back to a terminal this interface left running in an environment, or opens one."""
    try:
        listed = await desk.asks("env.term.list")
    except Exception as why:  # noqa: BLE001 -- said
        desk.reach.say(f"hmz: {why}", "red")
        return
    alive = [
        one
        for one in listed.get("terms") or ()
        if one.get("alive", True) and one.get("env", desk.id) == desk.id
    ]
    term = ""
    if alive:
        picked = await host.push_screen_wait(Terminals(alive))
        if picked is None:
            return
        term = "" if picked == _NEW else picked
    await _shell(host, desk, term)


class _Page(_Listing):
    """One page of an environment: `tab` and `shift+tab` step to the next and the last."""

    #: Which page this is.
    PAGE: ClassVar[str] = ""
    READS: ClassVar = True
    BINDINGS: ClassVar = [
        Binding("tab", "page(1)", "next page", show=False, priority=True),
        Binding("shift+tab", "page(-1)", "last page", show=False, priority=True),
    ]

    def __init__(self, desk: Desk, host: App[Any]) -> None:
        super().__init__()
        self._desk = desk
        self._host = host

    def crumb(self) -> str:
        title = next(title for name, title, _ in PANELS if name == self.PAGE)
        return f"{self._desk.named} · {title}"

    def page_keys(self) -> list[Key]:
        """`tab`, where there is another page to step to."""
        return [Key("tab", "page")] if len(panels_of(self._desk.env)) > 1 else []

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "page":
            return not self.typing() and not self._editing
        return super().check_action(action, parameters)

    def action_page(self, by: int) -> None:
        pages = panels_of(self._desk.env)
        if self.PAGE not in pages or len(pages) < 2:  # noqa: PLR2004 -- one to step to
            return
        going = pages[(pages.index(self.PAGE) + by) % len(pages)]
        self.dismiss(None)
        opens_page(self._host, self._desk, going)


#: What the row that opens a new terminal answers with: a byte no terminal's id has.
_NEW = "\x1dnew"


class Terminals(_Listing):
    """The terminals left running in an environment, and a new one."""

    asked = "Terminal"
    about = "Come back to a shell left running here, or open another."
    SEARCHES: ClassVar = False

    def __init__(self, alive: Sequence[Mapping[str, Any]]) -> None:
        super().__init__()
        self._rows_now = [
            _Row(_NEW, "new shell", "a login shell of its own"),
            *(
                _Row(
                    str(one.get("term")),
                    str(one.get("title") or one.get("term")),
                    f"{one.get('cols')}×{one.get('rows')}",
                )
                for one in alive
            ),
        ]


# -- Files --------------------------------------------------------------------------------------


class Named(Form[str]):
    """One thing to write: a name, a query, a message."""

    def __init__(self, title: str, label: str, about: str, value: str = "") -> None:
        """Asks for one thing.

        Args:
          title: What is asked, across the top.
          label: What the row is called.
          about: What it asks, beside it.
          value: What it says to begin with.
        """
        super().__init__()
        self._title = title
        self._label = label
        self._about = about
        self._typed_in = {"value": value}
        if value:
            self._fresh = {"value"}

    def asked(self) -> list[Question]:
        return [
            Question(
                "value",
                self._label,
                self._about,
                needed=not self._typed_in.get("value", "").strip(),
            )
        ]

    def _ask(self) -> None:
        self.query_one("#asked", Label).update(escape(self._title))
        self.query_one("#about", Label).update("")
        self._fill()

    def action_done(self) -> None:
        said = self._typed_in.get("value", "").strip()
        if not said:
            self._wrong = f"{self._label} is required"
            self._fill()
            return
        self.dismiss(said)


#: The stylesheet of a box of this module's, by its name.
_BOX = """
{name} {{ align: center middle; background: transparent; }}
{name} #sheet {{ width: 66; max-width: 100%; height: auto; padding: 1 2;
    border: round $primary; background: $background; }}
{name} #top {{ height: auto; }}
{name} #asked {{ width: 1fr; }}
{name} #about {{ padding: 0; }}
{name} #choices {{ display: none; }}
{name} #tuning {{ display: none; }}
{name} #pending {{ display: none; }}
{name} #spacer {{ display: none; }}
"""


class Sure(Popup):
    """Whether to do something that cannot be taken back."""

    CSS = _BOX.format(name="Sure")

    def __init__(self, asked: str, about: str = "", doing: str = "yes") -> None:
        """Asks.

        Args:
          asked: The question.
          about: What doing it does.
          doing: What the button that does it says.
        """
        super().__init__()
        self.asked = escape(asked)
        self.about = escape(about)
        self._doing = doing

    def rows(self) -> list[tuple[str, str, str]]:
        return [("yes", self._doing, "do it"), ("no", "cancel", "leave it as it is")]


#: What the question about a write refused as a conflict is answered with.
RELOAD, KEEP, COMPARE = "reload", "keep", "compare"


class Conflict(Popup):
    """What to do about a file that changed on disk since it was read."""

    CSS = _BOX.format(name="Conflict")

    def __init__(self, path: str) -> None:
        """Asks about one file.

        Args:
          path: The file.
        """
        super().__init__()
        self.asked = f"{escape(path)} changed on disk"
        self.about = "Since it was read, something else wrote it."

    def rows(self) -> list[tuple[str, str, str]]:
        return [
            (RELOAD, "reload", "throw yours away and read it again"),
            (KEEP, "keep mine", "write yours over it"),
            (COMPARE, "show diff", "what is on disk against yours"),
        ]


class Diff(ModalScreen[None]):
    """A diff, coloured, to read and leave."""

    DEFAULT_CSS = """
    Diff { background: $background; }
    Diff #title { height: 1; padding: 0 1; color: $accent; text-style: bold; }
    Diff #diff { height: 1fr; }
    Diff #keys { height: 1; padding: 0 1; color: $text-muted; }
    """
    BINDINGS: ClassVar = [
        Binding("escape", "dismiss", "back", show=False, priority=True),
        Binding("q", "dismiss", "back", show=False),
    ]

    def __init__(self, title: str, diff: str) -> None:
        """Shows one diff.

        Args:
          title: What it is of.
          diff: The unified diff.
        """
        super().__init__()
        self._title = title
        self._diff = diff

    def compose(self) -> ComposeResult:
        yield Label(escape(self._title), id="title")
        with VerticalScroll(id="diff"):
            yield Static(
                Syntax(self._diff, "diff", word_wrap=False)
                if self._diff
                else "no difference",
                id="body",
            )
        yield Label("[b $accent]esc[/] back", id="keys")


class Files(_Page):
    """One directory of an environment, its folders first: open, make, rename, remove."""

    PAGE: ClassVar = "files"
    TICKS: ClassVar = False
    BINDINGS: ClassVar = [
        Binding("n", "new_file", "new file", show=False),
        Binding("N", "new_folder", "new folder", show=False),
        Binding("r", "rename", "rename", show=False),
        Binding("d", "delete", "delete", show=False),
        Binding("e", "outside", "editor", show=False),
        Binding("ctrl+p", "quick", "open", show=False),
        Binding("question_mark", "find", "search", show=False),
        Binding("ctrl+shift+f", "find", "search", show=False),
    ]

    #: Its own keys, which are letters, and so typing while the search box is open.
    _OWN = frozenset(
        {"new_file", "new_folder", "rename", "delete", "outside", "quick", "find"}
    )

    def __init__(self, desk: Desk, host: App[Any], path: str = "") -> None:
        """Opens on one directory.

        Args:
          desk: The environment.
          host: The interface, which an editor of your own hands its terminal over from.
          path: The directory, or "" for where the environment works.
        """
        super().__init__(desk, host)
        self._path = path or desk.workdir
        self.asked = f"{desk.named}: {self._path}"
        self.about = ""
        self._entries: dict[str, Mapping[str, Any]] = {}

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in self._OWN:
            return not self.typing() and not self._editing
        return super().check_action(action, parameters)

    def keys(self) -> list[Key]:
        return [
            Key("enter", "open"),
            Key("backspace", "up"),
            Key("n", "file"),
            Key("N", "folder"),
            Key("r", "rename"),
            Key("d", "delete"),
            Key("e", "$EDITOR"),
            Key("ctrl+p", "open…"),
            Key("?", "find"),
            *self.page_keys(),
            Key("esc", "back"),
        ]

    def on_mount(self) -> None:
        self.lists(self._path)

    def on_screen_resume(self) -> None:
        if self._entries:
            self.lists(self._path, keep=True)

    def lists(self, path: str, *, keep: bool = False, landing: str = "") -> None:
        """Reads one directory, and lists it.

        Args:
          path: The directory.
          keep: Whether the cursor stays where it was, as it does when the same one is read
            again.
          landing: The name to put the cursor on, or "".
        """
        self.run_worker(self._lists(path, keep, landing), group="list", exclusive=True)

    async def _lists(self, path: str, keep: bool, landing: str) -> None:  # noqa: FBT001
        try:
            said = await self._desk.asks("env.list", path=path)
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        was = self._path
        self._path = str(said.get("path") or path)
        # Directories first, as the host lists them -- and as it is listed here whatever it does.
        entries = sorted(
            said.get("entries") or (), key=lambda one: one.get("kind") != "dir"
        )
        self._entries = {str(one.get("name")): one for one in entries}
        rows: list[_Row] = []
        for one in entries:
            name, kind = str(one.get("name")), str(one.get("kind") or "file")
            if kind == "dir":
                rows.append(_Row(name, f"{name}/", "folder"))
            elif kind == "link":
                rows.append(_Row(name, f"{name}@", f"→ {one.get('target') or '?'}"))
            else:
                rows.append(_Row(name, name, _sized(int(one.get("size") or 0))))
        self.asked = f"{self._desk.named}: {self._path}"
        if not keep or was != self._path:
            self._current = landing or posixpath.basename(was.rstrip("/"))
            if self.is_mounted:
                self.query_one("#choices", OptionList).clear_options()
        if self._searching:
            self._clears_search()
        # The same directory read again keeps what was said under it: why a file did not open.
        self.shows(rows, self._said if keep else "")
        self._current = ""

    def nothing(self) -> str:
        return "" if self._rows_now else "[$text-muted]nothing here[/]"

    def _at(self, name: str) -> str:
        return posixpath.join(self._path, name)

    def _edits(self, path: str, line: int = 0) -> None:
        """Opens one file in the editor; one it will not open is said under the list."""
        entry = self._entries.get(posixpath.basename(path), {})
        if (
            posixpath.dirname(path) == self._path
            and int(entry.get("size") or 0) > LARGE
        ):
            self.fails(f"{posixpath.basename(path)} is larger than 5 MiB: {_OUTSIDE}")
            return
        self._interface().push_screen(
            Editing(self._desk, path, self._host, line=line),
            lambda why: self.fails(why) if why else None,
        )

    def chosen(self, row: str) -> None:
        kind = self._entries.get(row, {}).get("kind")
        if kind == "dir":
            self.lists(self._at(row))
        elif kind == "link":
            self.run_worker(self._follows(row), group="list", exclusive=True)
        else:
            self._edits(self._at(row))

    async def _follows(self, row: str) -> None:
        """Opens a link: listed where it leads to a directory, edited where to a file."""
        try:
            await self._desk.asks("env.list", path=self._at(row))
        except Exception:  # noqa: BLE001 -- not a directory, so a file to edit
            self._edits(self._at(row))
            return
        self.lists(self._at(row))

    def action_up(self) -> None:
        if self._path in ("/", ""):
            self.leaving()
            return
        self.lists(posixpath.dirname(self._path.rstrip("/")) or "/")

    def action_new_file(self) -> None:
        self.run_worker(self._makes(folder=False), group="do")

    def action_new_folder(self) -> None:
        self.run_worker(self._makes(folder=True), group="do")

    def action_rename(self) -> None:
        if row := self.under():
            self.run_worker(self._renames(row), group="do")

    def action_delete(self) -> None:
        if row := self.under():
            self.run_worker(self._removes(row), group="do")

    def action_outside(self) -> None:
        row = self.under()
        if row and self._entries.get(row, {}).get("kind") != "dir":
            self.run_worker(_outside(self._host, self._desk, self._at(row)), group="do")

    def action_quick(self) -> None:
        self.run_worker(self._quick(), group="do")

    def action_find(self) -> None:
        self.run_worker(self._finds(), group="do")

    async def _makes(self, *, folder: bool) -> None:
        what = "folder" if folder else "file"
        named = await self._interface().push_screen_wait(
            Named(f"New {what} in {self._path}", "name", f"what the {what} is called")
        )
        if not named:
            return
        path = self._at(named)
        try:
            if folder:
                await self._desk.asks("env.mkdir", path=path)
            else:
                await self._desk.asks("env.write", path=path, data="", if_match="")
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        self.lists(self._path, landing=named.split("/")[0])
        if not folder:
            self._edits(path)

    async def _renames(self, row: str) -> None:
        named = await self._interface().push_screen_wait(
            Named(f"Rename {row}", "name", "what it is called now", row)
        )
        if not named or named == row:
            return
        try:
            await self._desk.asks("env.rename", path=self._at(row), to=self._at(named))
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        self.lists(self._path, landing=named)

    async def _removes(self, row: str) -> None:
        folder = self._entries.get(row, {}).get("kind") == "dir"
        sure = await self._interface().push_screen_wait(
            Sure(
                f"Delete {row}?",
                "Everything in it goes too; this cannot be undone."
                if folder
                else "This cannot be undone.",
                "delete",
            )
        )
        if sure != "yes":
            return
        try:
            await self._desk.asks("env.remove", path=self._at(row))
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        self._said = ""
        self.lists(self._path, keep=True)

    async def _quick(self) -> None:
        try:
            found = await self._desk.asks("env.find")
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        picked = await self._interface().push_screen_wait(
            Opens(
                [str(one) for one in found.get("paths") or ()],
                truncated=bool(found.get("truncated")),
            )
        )
        if picked:
            path = (
                picked
                if picked.startswith("/")
                else posixpath.join(self._desk.workdir, picked)
            )
            self._edits(path)

    async def _finds(self) -> None:
        query = await self._interface().push_screen_wait(
            Named(f"Search {self._desk.named}", "text", "what to look for in its files")
        )
        if not query:
            return
        try:
            found = await self._desk.asks("env.search", query=query)
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        matches = list(found.get("matches") or ())
        picked = await self._interface().push_screen_wait(
            Matches(query, matches, truncated=bool(found.get("truncated")))
        )
        if not picked:
            return
        path, _, line = picked.rpartition(_SEP)
        path = (
            path if path.startswith("/") else posixpath.join(self._desk.workdir, path)
        )
        self._edits(path, int(line or 0))


class Opens(_Listing):
    """Every file of an environment, narrowed by typing, to open one."""

    asked = "Open a file"

    def __init__(self, paths: Sequence[str], *, truncated: bool = False) -> None:
        super().__init__()
        self.about = f"{len(paths)} files" + (
            ", and more not listed" if truncated else ""
        )
        self._rows_now = [_Row(one, one) for one in paths]

    def on_mount(self) -> None:
        # After the sheet's own, which puts the focus on the list.
        self.call_after_refresh(self.action_search)


class Matches(_Listing):
    """Every line a search found, to open a file at one."""

    asked = "Found"

    def __init__(
        self,
        query: str,
        matches: Sequence[Mapping[str, Any]],
        *,
        truncated: bool = False,
    ) -> None:
        super().__init__()
        self.about = f"{len(matches)} lines with {query!r}" + (
            ", and more not listed" if truncated else ""
        )
        self._rows_now = [
            _Row(
                f"{one.get('path')}{_SEP}{one.get('line')}",
                f"{one.get('path')}:{one.get('line')}",
                str(one.get("text") or "").strip(),
            )
            for one in matches
        ]

    def nothing(self) -> str:
        return "" if self._rows_now else "[$text-muted]nothing found[/]"


async def _outside(host: App[Any], desk: Desk, path: str) -> None:
    """Edits one file in the editor you set, on a copy, and writes it back."""
    try:
        await _edits_outside(host, desk, path)
    except Exception as why:  # noqa: BLE001 -- an editor not there, a host gone: said
        desk.reach.say(f"hmz: {why}", "red")


async def _edits_outside(host: App[Any], desk: Desk, path: str) -> None:
    say = desk.reach.say
    read = await _read(desk, path, cap=sys.maxsize)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    with tempfile.TemporaryDirectory(prefix="hmz-env-") as kept:
        copy = Path(kept) / (posixpath.basename(path) or "file")
        copy.write_bytes(read.data)
        with handed_over(cast("App[None]", host)):
            # Waited on where it stands, as a shell is: the terminal is the editor's now.
            subprocess.call([*shlex.split(editor), str(copy)])  # noqa: ASYNC221
        after = copy.read_bytes()
    if after == read.data:
        return
    etag: str | None = read.etag
    while True:
        try:
            await desk.asks("env.write", path=path, data=_encoded(after), if_match=etag)
        except Exception as why:  # noqa: BLE001 -- a conflict is asked about, the rest said
            if not _conflicted(why):
                say(f"hmz: {why}", "red")
                return
            answer = await host.push_screen_wait(Conflict(path))
            if answer == KEEP:
                etag = None
                continue
            if answer == COMPARE:
                now = await _read(desk, path, cap=sys.maxsize)
                await host.push_screen_wait(
                    Diff(f"{path}: on disk → yours", unified(now.data, after, path))
                )
                continue
            say(f"{path}: kept what is on disk; your edit was dropped", "dim")
            return
        say(f"saved {path} in {desk.named}", "dim")
        return


#: Why a file is not opened in the editor here, and what opens it instead.
_OUTSIDE = "e opens it in your own editor"


class Editing(ModalScreen[str | None]):
    """One file of an environment, in a code editor that saves itself a second after an edit."""

    DEFAULT_CSS = """
    Editing { background: $background; }
    Editing #code { height: 1fr; border: none; }
    Editing #status { height: 1; padding: 0 1; background: $panel; }
    """
    BINDINGS: ClassVar = [
        Binding("ctrl+s", "save", "save", show=False, priority=True),
        Binding("escape", "close", "close", show=False, priority=True),
    ]

    def __init__(self, desk: Desk, path: str, host: App[Any], *, line: int = 0) -> None:
        """Opens one file.

        Args:
          desk: The environment.
          path: The file.
          host: The interface.
          line: The line to put the cursor on, from 1, or 0 for the top.
        """
        super().__init__()
        self._desk = desk
        self._path = path
        self._host = host
        self._line = line
        self._etag: str | None = None
        self._saved = ""
        self._loaded = False
        self._state = "Reading…"
        self._timer: Timer | None = None
        self._lock = asyncio.Lock()
        self._conflict = False
        self._leaving = False

    def _ui(self) -> App[None]:
        """The interface this editor is drawn over."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    @property
    def path(self) -> str:
        """The file."""
        return self._path

    @property
    def state(self) -> str:
        """What the status line says of saving: Saving…, Saved, a conflict, an error."""
        return self._state

    def compose(self) -> ComposeResult:
        yield TextArea.code_editor("", id="code", read_only=True)
        yield Static(id="status")

    def on_mount(self) -> None:
        self._says()
        self.run_worker(self._loads(), group="load", exclusive=True)

    def _area(self) -> TextArea:
        return self.query_one("#code", TextArea)

    async def _loads(self) -> None:
        area = self._area()
        try:
            read = await _read(self._desk, self._path)
        except Exception as why:  # noqa: BLE001 -- said on the status line
            self._state = str(why)
            self._says()
            return
        named = posixpath.basename(self._path)
        if not read.whole:
            self.dismiss(f"{named} is {_sized(read.size)}: {_OUTSIDE}")
            return
        try:
            if b"\0" in read.data[:8192]:
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "a NUL")  # noqa: TRY301
            text = read.data.decode("utf-8")
        except UnicodeDecodeError:
            self.dismiss(f"{named} is not text: {_OUTSIDE}")
            return
        self._etag = read.etag
        self._saved = text
        language = language_of(self._path, sorted(area.available_languages))
        area.load_text(text)
        area.language = language
        area.read_only = False
        self._loaded = True
        self._state = ""
        if self._line > 0:
            area.move_cursor((self._line - 1, 0), center=True)
        area.focus()
        self._says()

    def _says(self) -> None:
        area = self._area()
        row, column = area.cursor_location
        dirty = self._loaded and area.text != self._saved
        state = self._state or ("● edited" if dirty else "")
        self.query_one("#status", Static).update(
            f"[b]{escape(self._path)}[/]  Ln {row + 1}, Col {column + 1}"
            + (f"  [$text-muted]{escape(state)}[/]" if state else "")
            + "   [$text-muted]ctrl+s save · esc close[/]"
        )

    @on(TextArea.SelectionChanged, "#code")
    def _moved(self) -> None:
        self._says()

    @on(TextArea.Changed, "#code")
    def _edited(self) -> None:
        if not self._loaded:
            return
        if self._state in ("Saved", ""):
            self._state = ""
        if self._timer is not None:
            self._timer.stop()
        self._timer = (
            None
            if self._conflict
            else self.set_timer(_IDLE, lambda: self.run_worker(self.saves()))
        )
        self._says()

    def dirty(self) -> bool:
        """Whether the editor holds what is not written yet."""
        return self._loaded and self._area().text != self._saved

    async def saves(self, *, over: bool = False) -> bool:
        """Writes what the editor holds, where it holds anything new; one write at a time.

        Args:
          over: Whether to write over whatever is there, as keeping yours after a conflict.

        Returns:
          Whether what the editor holds is written now.
        """
        async with self._lock:
            text = self._area().text
            if not self.dirty() and not over:
                return True
            if self._conflict and not over:
                return False
            self._state = "Saving…"
            self._says()
            try:
                said = await self._desk.asks(
                    "env.write",
                    path=self._path,
                    data=_encoded(text.encode("utf-8")),
                    if_match=None if over else self._etag,
                )
            except Exception as why:  # noqa: BLE001 -- a conflict is asked about
                if _conflicted(why):
                    self._conflict = True
                    self._state = "conflict: changed on disk"
                    self._says()
                    self.run_worker(self._resolves(), group="conflict", exclusive=True)
                else:
                    self._state = f"not saved: {why}"
                    self._says()
                return False
            self._etag = str(said.get("etag") or "")
            self._saved = text
            self._conflict = False
            self._state = "Saved"
            self._says()
        if self.dirty():
            # Typed into while it was being written: what was typed is written next.
            return await self.saves()
        return True

    async def _resolves(self) -> None:
        """Asks what to do about a write refused because the file changed on disk."""
        while self._conflict:
            answer = await self._ui().push_screen_wait(Conflict(self._path))
            if answer == RELOAD:
                self._conflict = self._leaving = False
                self._loaded = False
                await self._loads()
                return
            if answer == KEEP:
                self._conflict = False
                if await self.saves(over=True) and self._leaving:
                    self.dismiss()
                return
            if answer == COMPARE:
                try:
                    disk = await _read(self._desk, self._path, cap=sys.maxsize)
                except Exception as why:  # noqa: BLE001 -- said on the status line
                    self._state = str(why)
                    self._says()
                    return
                mine = self._area().text.encode("utf-8")
                await self._ui().push_screen_wait(
                    Diff(
                        f"{self._path}: on disk → yours",
                        unified(disk.data, mine, self._path),
                    )
                )
                continue
            self._leaving = False
            return

    async def action_save(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._conflict:
            self.run_worker(self._resolves(), group="conflict", exclusive=True)
            return
        await self.saves()

    def action_close(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._leaving = True
        if self._conflict:
            self.run_worker(self._resolves(), group="conflict", exclusive=True)
            return
        self.run_worker(self._closes(), group="close", exclusive=True)

    async def _closes(self) -> None:
        """Saves what is held, then closes; a conflict asks first, and keeps it open.

        A write that failed for any other reason -- the host gone, the disk full -- asks
        whether to close without it, rather than holding the editor open for good.
        """
        if await self.saves():
            if self._leaving:
                self.dismiss()
            return
        if self._conflict:
            return
        sure = await self._ui().push_screen_wait(
            Sure(
                f"Close {posixpath.basename(self._path)} without saving?",
                self._state,
                "close",
            )
        )
        if sure == "yes":
            self.dismiss()
        else:
            self._leaving = False


# -- Changes and snapshots ----------------------------------------------------------------------


class Commit(Form[tuple[str, bool]]):
    """What to commit the staged changes as, and whether as the last commit again."""

    def __init__(self) -> None:
        super().__init__()
        self._typed_in = {"message": "", "amend": "off"}

    def asked(self) -> list[Question]:
        return [
            Question(
                "message",
                "message",
                "what the commit says",
                needed=not self._typed_in.get("message", "").strip(),
            ),
            Question("amend", "amend", "replace the last commit instead", kind="steps"),
        ]

    def choices(self, held: str) -> Sequence[str]:
        return ("off", "on") if held == "amend" else ()

    def lines(self, held: str) -> bool:
        return held == "message"

    def done_about(self) -> str:
        return "commits what is staged"

    def _ask(self) -> None:
        self.query_one("#asked", Label).update("Commit")
        self.query_one("#about", Label).update("")
        self._fill()

    def action_done(self) -> None:
        said = self._typed_in.get("message", "").strip()
        amend = self._typed_in.get("amend") == "on"
        if not said:
            self._wrong = "message is required"
            self._fill()
            return
        self.dismiss((said, amend))


class Changes(_Page):
    """An environment's git changes, as a source-control view groups them."""

    PAGE: ClassVar = "changes"
    BINDINGS: ClassVar = [
        Binding("s", "stage", "stage", show=False),
        Binding("u", "unstage", "unstage", show=False),
        Binding("x", "discard", "discard", show=False),
        Binding("c", "commit", "commit", show=False),
        Binding("r", "refresh", "refresh", show=False),
    ]
    _OWN = frozenset({"stage", "unstage", "discard", "commit", "refresh"})

    def __init__(self, desk: Desk, host: App[Any]) -> None:
        """Opens on one environment's changes.

        Args:
          desk: The environment.
          host: The interface.
        """
        super().__init__(desk, host)
        self.asked = f"{desk.named}: changes"
        self._stops: Callable[[], None] = lambda: None
        self._files: list[Mapping[str, Any]] = []

    def crumb(self) -> str:
        return "Changes"

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in self._OWN:
            return not self.typing() and not self._editing
        return super().check_action(action, parameters)

    def keys(self) -> list[Key]:
        return [
            Key("enter", "diff"),
            Key("s", "stage"),
            Key("u", "unstage"),
            Key("x", "discard"),
            Key("c", "commit"),
            Key("r", "refresh"),
            *self.page_keys(),
            Key("esc", "back"),
        ]

    def actions(self) -> list[Action]:
        return [
            Action("stage-all", "stage all", "stage every change", self._stages_all),
            Action(
                "unstage-all", "unstage all", "unstage everything", self._unstages_all
            ),
            Action("commit", "commit…", "commit what is staged", self.action_commit),
            *super().actions(),
        ]

    def on_mount(self) -> None:
        self.action_refresh()
        self._stops = self._desk.reach.watching(self.action_refresh)

    def on_unmount(self) -> None:
        self._stops()

    def action_refresh(self) -> None:
        self.run_worker(self._reads(), group="status", exclusive=True)

    async def _reads(self) -> None:
        try:
            said = await self._desk.asks("env.git.status")
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        self._files = list(said.get("files") or ())
        branch = str(said.get("branch") or "")
        head = str(said.get("head") or "")[:7]
        upstream = str(said.get("upstream") or "")
        self.about = _DOT.join(
            one
            for one in (
                branch or (f"detached at {head}" if head else ""),
                f"↑{said.get('ahead') or 0} ↓{said.get('behind') or 0} {upstream}".strip()
                if upstream
                else "",
                str(said.get("root") or ""),
            )
            if one
        )
        rows: list[_Row] = []
        for group, files in grouped(self._files):
            rows.append(
                _Row(f"{_HEADING}{group}", f"{group} ({len(files)})", heading=True)
            )
            for one in files:
                path = str(one.get("path"))
                code = (
                    "U"
                    if group == _CONFLICTS
                    else "?"
                    if group == "Untracked"
                    else str(one.get("index" if group == _STAGED else "worktree"))
                )
                orig = one.get("orig")
                rows.append(
                    _Row(
                        f"{group}{_SEP}{path}",
                        path,
                        code + (f"  ← {orig}" if orig else ""),
                    )
                )
        self.shows(rows)

    def nothing(self) -> str:
        return "" if self._rows_now else "[$text-muted]no changes[/]"

    def _under(self) -> tuple[str, str]:
        group, _, path = self.under().partition(_SEP)
        return group, path

    def chosen(self, row: str) -> None:
        group, _, path = row.partition(_SEP)
        if path:
            self.run_worker(self._diffs(path, staged=group == _STAGED), group="do")

    async def _diffs(self, path: str, *, staged: bool) -> None:
        try:
            said = await self._desk.asks("env.git.diff", path=path, staged=staged)
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        if said.get("binary"):
            text = ""
            title = f"{path}: binary"
        else:
            old, new = said.get("old"), said.get("new")
            text = unified(
                None if old is None else _decoded(old),
                None if new is None else _decoded(new),
                path,
            )
            title = f"{path} ({'staged' if staged else 'working tree'})"
        await self._interface().push_screen_wait(Diff(title, text))

    async def _does(self, method: str, /, **params: Any) -> None:
        try:
            await self._desk.asks(method, **params)
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        self._said = ""
        await self._reads()

    def action_stage(self) -> None:
        group, path = self._under()
        if path and group != _STAGED:
            self.run_worker(self._does("env.git.stage", paths=[path]), group="do")

    def action_unstage(self) -> None:
        group, path = self._under()
        if path and group == _STAGED:
            self.run_worker(self._does("env.git.unstage", paths=[path]), group="do")

    def action_discard(self) -> None:
        group, path = self._under()
        if path and group != _STAGED:
            self.run_worker(
                self._discards(path, untracked=group == "Untracked"), group="do"
            )

    async def _discards(self, path: str, *, untracked: bool) -> None:
        sure = await self._interface().push_screen_wait(
            Sure(
                f"Discard changes to {path}?",
                "The file is deleted; this cannot be undone."
                if untracked
                else "Its changes are lost; this cannot be undone.",
                "discard",
            )
        )
        if sure == "yes":
            await self._does("env.git.discard", paths=[path])

    def _stages_all(self) -> None:
        paths = sorted(
            {
                str(one.get("path"))
                for group, files in grouped(self._files)
                if group != _STAGED
                for one in files
            }
        )
        if paths:
            self.run_worker(self._does("env.git.stage", paths=paths), group="do")

    def _unstages_all(self) -> None:
        paths = sorted(
            {
                str(one.get("path"))
                for group, files in grouped(self._files)
                if group == _STAGED
                for one in files
            }
        )
        if paths:
            self.run_worker(self._does("env.git.unstage", paths=paths), group="do")

    def action_commit(self) -> None:
        self.run_worker(self._commits(), group="do")

    async def _commits(self) -> None:
        said = await self._interface().push_screen_wait(Commit())
        if said is None:
            return
        message, amend = said
        await self._does("env.git.commit", message=message, amend=amend)


class Snapshots(_Page):
    """The snapshots an environment can be rewound to."""

    PAGE: ClassVar = "snapshots"
    SEARCHES: ClassVar = False

    def __init__(self, desk: Desk, host: App[Any]) -> None:
        """Opens on one environment's snapshots.

        Args:
          desk: The environment.
          host: The interface.
        """
        super().__init__(desk, host)
        self.asked = f"{desk.named}: snapshots"
        self.about = "Rewinding puts its files back as they were at that snapshot."

    def keys(self) -> list[Key]:
        return [Key("enter", "rewind"), *self.page_keys(), Key("esc", "back")]

    def on_mount(self) -> None:
        self.run_worker(self._reads(), group="list", exclusive=True)

    async def _reads(self) -> None:
        try:
            said = await self._desk.asks("env.git.snapshots")
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        refs = [str(one) for one in said.get("snapshots") or ()]
        self.shows([_Row(one, one) for one in refs], self._said)

    def nothing(self) -> str:
        return "" if self._rows_now else "[$text-muted]no snapshots yet[/]"

    def chosen(self, row: str) -> None:
        self.run_worker(self._rewinds(row), group="do")

    async def _rewinds(self, ref: str) -> None:
        sure = await self._interface().push_screen_wait(
            Sure(
                f"Rewind {self._desk.named} to {ref}?",
                "Its files go back as they were then; later changes are lost.",
                "rewind",
            )
        )
        if sure != "yes":
            return
        try:
            await self._desk.asks("env.git.rewind", ref=ref)
        except Exception as why:  # noqa: BLE001 -- the guard's refusal, said
            self.fails(why)
            return
        self._said = ""
        self._desk.reach.say(f"rewound {self._desk.named} to {ref}", "dim")
        self.dismiss(None)


def _matching(
    envs: Sequence[Mapping[str, Any]], named: str
) -> Mapping[str, Any] | None:
    """The environment `/env <role>` means: by id, chain or role, an open one first."""
    found = [
        one
        for one in envs
        if named in (one.get("id"), one.get("chain"), one.get("role"))
    ]
    found.sort(
        key=lambda one: (not one.get("open", True), one.get("parent") is not None)
    )
    return found[0] if found else None


def opens_env(host: App[Any], reach: Reach, named: str = "") -> str:
    """Opens `/env`: the environments, and one's first page where it is named.

    Args:
      host: The interface.
      reach: The host.
      named: The role, chain or id given after `/env`, or "".

    Returns:
      What is wrong with what was given, or "" once it is open.
    """
    envs = reach.envs()
    env = _matching(envs, named) if named else None
    if named and env is None:
        roles = sorted({str(one.get("role")) for one in envs})
        return f"/env: no environment {named!r} here; choose {', '.join(roles)}"
    host.push_screen(Envs(reach, host))
    if env is not None:
        opens_page(host, Desk(env, reach), default_panel(env))
    return ""
