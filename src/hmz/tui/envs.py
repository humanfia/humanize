"""`/env`: what each environment of the epic or chat in front of you can do, from here.

Every environment a run uses -- a role's workspace, one derived from it, a chat's own -- is
listed by the host in its `envs` snapshot, with the capabilities its driver really has. Each
of those is a panel here: its files, browsed and edited in a code editor that saves itself;
its git changes, grouped as a source-control view groups them, staged and committed from the
list; its snapshots, rewound to; and a shell in it, which is this terminal handed over to a
terminal in the environment until `~.` or the shell ending hands it back.

The same three -- files, changes, terminal -- are panes too (:class:`FilesPane`,
:class:`ChangesPane`, :class:`TerminalPane`): widgets that sit in a zone beside the log
(`hmz.tui.views.envpanes`), so that what an agent says and what it changed are read side by
side. A pane and its sheet ask the host the same things and read the answers with the same
functions here; what differs is where they are drawn. A pane's terminal is drawn by a
terminal emulator in the pane (:class:`Tty`) rather than handed the whole screen.

What is said to the host is the `env.*` methods, made through the interface's own link with
the epic's subscription: the same session the rest of the epic is reached through, so that a
terminal's output -- which reaches only the frontend that opened it -- comes back here.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import difflib
import functools
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
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Self, cast

import pyte
from rich.cells import cell_len
from rich.markup import escape
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from hmz.words import t

from . import humanfia
from .pick import Action, Form, Key, Popup, Question, Sheet, handed_over
from .shell import Zone

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual import events
    from textual.app import App, ComposeResult
    from textual.timer import Timer

__all__ = [
    "ACK_EVERY",
    "CHUNK",
    "LARGE",
    "PANELS",
    "VIEWED",
    "Changes",
    "ChangesPane",
    "Commit",
    "Conflict",
    "Credit",
    "Desk",
    "Diff",
    "Editing",
    "Envs",
    "Escape",
    "Files",
    "FilesPane",
    "Inbox",
    "Matches",
    "Named",
    "Opens",
    "Pane",
    "Reach",
    "Read",
    "Snapshots",
    "Sure",
    "TerminalPane",
    "Terminals",
    "Tty",
    "Viewing",
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
    ("shell", "Terminal", ("shell",)),
    ("snapshots", "Snapshots", ("rewind",)),
)

#: How much of a file one `env.read` asks for, which is the most the host gives at once.
CHUNK = 1024 * 1024

#: How large a file is still edited here; a larger one is not opened in the editor.
LARGE = 5 * 1024 * 1024

#: How large a file is still read in a pane, which colours all of it at once.
VIEWED = CHUNK

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
        of: Callable[[], str] = lambda: "",
    ) -> None:
        """Holds how to reach the host.

        Args:
          ask: What asks the host one thing, `do` and what it takes, and answers or raises
            the refusal.
          envs: The environments as the host last said they stand.
          say: What puts a line on the interface's transcript, in a style.
          of: The chat or epic the environments are of now, by its id, or "" for none.
        """
        self._ask = ask
        self._envs = envs
        self.say = say
        self._of = of
        #: The environment the panes of each chat or epic were last turned to, by its id.
        self._turned: dict[str, str] = {}
        self._watchers: list[Callable[[], None]] = []
        self._viewers: list[Viewing] = []
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

    def desks(self, page: str) -> list[Desk]:
        """The open environments that have one page, in the order `/env` lists them.

        Args:
          page: `files`, `changes`, `shell` or `snapshots`.

        Returns:
          Each as a pane works on it; none where no environment here has that page.
        """
        return [
            Desk(one, self)
            for _, one in tree(self.envs())
            if one.get("open", True) and page in panels_of(one)
        ]

    def desk(self, page: str) -> Desk | None:
        """The environment a pane of one page shows: the one turned to, else the first.

        Args:
          page: `files`, `changes`, `shell` or `snapshots`.

        Returns:
          It, or None where no open environment here has that page.
        """
        desks = self.desks(page)
        turned = self._turned.get(self._of())
        return next(
            (one for one in desks if one.id == turned), desks[0] if desks else None
        )

    def turns(self, env: str) -> None:
        """Turns the panes of the chat or epic in front to one environment, and remembers it.

        Args:
          env: The environment, by its id.
        """
        self._turned[self._of()] = env

    def views(self, viewing: Viewing) -> Callable[[], None]:
        """Hands a terminal's messages to a pane that draws it, until told not to.

        Args:
          viewing: Which terminal, and what takes its messages.

        Returns:
          What stops them being handed over.
        """
        with self._lock:
            self._viewers.append(viewing)

        def stops() -> None:
            with self._lock, contextlib.suppress(ValueError):
                self._viewers.remove(viewing)

        return stops

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
        """Takes a terminal's message: the bridge's, a pane's, or, with neither, nobody's.

        A terminal left running is still one this frontend watches, and the host stops it
        once its output goes unacknowledged; so what nobody is reading is acknowledged here.
        A pane still opening a terminal is handed every terminal's, since a new shell's
        prompt may be told before the answer saying which it is, and is told whether what
        it is handed is acknowledged here already.

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
            viewers = list(self._viewers)
        if bridged is not None and bridged.term in (term, ""):
            bridged.put(dict(message))
            return True
        drawn = any(one.term == term for one in viewers)
        for one in viewers:
            if one.term in (term, ""):
                one.hears(dict(message), not drawn)
        if drawn:
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


class Viewing:
    """One terminal as a pane draws it: which it is, and what is handed its messages.

    Attributes:
      term: The terminal, or "" while it is being opened, which takes any terminal's.
      hears: What takes a message, on whatever thread it was told on, and whether the bytes
        it carries are acknowledged to the host already.
    """

    def __init__(
        self, hears: Callable[[dict[str, Any], bool], None], term: str = ""
    ) -> None:
        """Watches one terminal.

        Args:
          hears: What takes its messages.
          term: The terminal, or "" for one still being opened.
        """
        self.hears = hears
        self.term = term


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
    raise OSError(t("{path} kept changing while it was being read", path=path))


# -- The shell ----------------------------------------------------------------------------------


class _Failed(str):
    """How a shell ended, where it ended because the terminal or the host was lost."""

    __slots__ = ()


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
                        return t(
                            "Exited with status {status}.", status=message.get("status")
                        )
                    if kind != "term":
                        continue
                    data = _decoded(message.get("data"))
                    _written(stdout, data)
                    if acked := credit.took(len(data)):
                        ask("env.term.ack", {"term": term, "bytes": acked})
            if stdin in ready:
                typed = os.read(stdin, 4096)
                if not typed:
                    return t("Left; it keeps running.")
                sent, leaves = escape_.typed(typed)
                if sent:
                    ask("env.term.input", {"term": term, "data": _encoded(sent)})
                if leaves:
                    return t("Left; it keeps running.")
    except Exception as why:  # noqa: BLE001 -- the terminal or the host gone, said
        return _Failed(t("Failed: {why}", why=why))
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
        say(
            "hmz: "
            + t(
                "A shell in {name} cannot be opened because hmz is not running in a "
                "terminal.",
                name=desk.named,
            ),
            "red",
        )
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
        t("Shell in {name}: {ended}", name=desk.named, ended=ended),
        "red" if isinstance(ended, _Failed) else "dim",
    )


# -- What a sheet and a pane read alike ---------------------------------------------------------


def _entries(said: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """One directory as `env.list` answered it, its folders first."""
    # Directories first, as the host lists them -- and as it is listed here whatever it does.
    return sorted(said.get("entries") or (), key=lambda one: one.get("kind") != "dir")


def _entry(one: Mapping[str, Any]) -> tuple[str, str]:
    """One entry of a directory as a row: what it is called, and the line about it."""
    name, kind = str(one.get("name")), str(one.get("kind") or "file")
    if kind == "dir":
        return f"{name}/", ""
    if kind == "link":
        return f"{name}@", f"→ {one.get('target') or '?'}"
    return name, _sized(int(one.get("size") or 0))


def _standing(said: Mapping[str, Any]) -> str:
    """Where a repository stands, in a line: its branch, its upstream, its top directory."""
    branch = str(said.get("branch") or "")
    head = str(said.get("head") or "")[:7]
    upstream = str(said.get("upstream") or "")
    return _DOT.join(
        one
        for one in (
            branch or (t("{commit} (detached)", commit=head) if head else ""),
            f"↑{said.get('ahead') or 0} ↓{said.get('behind') or 0} {upstream}".strip()
            if upstream
            else "",
            str(said.get("root") or ""),
        )
        if one
    )


def _changed(files: Sequence[Mapping[str, Any]]) -> list[_Row]:
    """The changed files as rows, a heading over each group that has any."""
    rows: list[_Row] = []
    for group, held in grouped(files):
        rows.append(
            _Row(f"{_HEADING}{group}", f"{t(group)} ({len(held)})", heading=True)
        )
        for one in held:
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
                    f"{group}{_SEP}{path}", path, code + (f"  ← {orig}" if orig else "")
                )
            )
    return rows


def _staged(files: Sequence[Mapping[str, Any]], path: str | None = None) -> list[str]:
    """The paths that unstage `path`, or all that is staged: a rename's old path too."""
    return sorted(
        {
            str(one[key])
            for group, held in grouped(files)
            if group == _STAGED
            for one in held
            if path in (None, str(one.get("path")))
            for key in ("path", "orig")
            if one.get(key)
        }
    )


def _unstaged(files: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every path with a change that is not staged, which staging all stages."""
    return sorted(
        {
            str(one.get("path"))
            for group, held in grouped(files)
            if group != _STAGED
            for one in held
        }
    )


class _Differed(NamedTuple):
    """One file's change, read: what it is headed, the diff, and what is said for none."""

    title: str
    diff: str
    said: str


async def _differed(desk: Desk, path: str, *, staged: bool) -> _Differed:
    """Reads one file's change off the host, as a unified diff or as why there is none."""
    said = await desk.asks("env.git.diff", path=path, staged=staged)
    title = f"{path}{_DOT}{t(_STAGED if staged else 'Changes')}"
    old, new = said.get("old"), said.get("new")
    if said.get("binary"):
        return _Differed(
            title,
            "",
            t(
                "{name} is a binary file ({before}, {after}): there is no text to compare.",
                name=posixpath.basename(path),
                before=_sized(len(_decoded(old))),
                after=_sized(len(_decoded(new))),
            ),
        )
    diff = unified(
        None if old is None else _decoded(old),
        None if new is None else _decoded(new),
        path,
    )
    return _Differed(title, diff, "" if diff else t("An empty diff."))


def _removing(name: str, *, folder: bool) -> Sure:
    """The box that asks before a file or a folder is deleted, naming it."""
    return Sure(
        t("Delete the folder {name} and everything in it?", name=name)
        if folder
        else t("Delete {name}?", name=name),
        "",
        t("Delete"),
    )


def _discarding(path: str, *, untracked: bool) -> Sure:
    """The box that asks before a file's changes are thrown away, naming it."""
    return Sure(
        t(
            "Delete the untracked file {name}? It is removed from the disk, and this "
            "cannot be undone.",
            name=path,
        )
        if untracked
        else t("Discard the changes to {name}? This cannot be undone.", name=path),
        "",
        t("Discard Changes"),
    )


def _rewinding(ref: str) -> Sure:
    """The box that asks before an environment is rewound, naming the snapshot."""
    return Sure(
        t(
            "Rewind this environment to {ref}? Its working tree is reset to that "
            "snapshot: every change made since, committed or not, is lost.",
            ref=ref,
        ),
        "",
        t("Rewind"),
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
        return [Key("enter", t("Open")), Key("esc", t("Back"))]

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
        self.asked = t("Environments")
        self.about = t("Every environment that this chat or epic uses.")
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
        return t("Environments")

    def on_mount(self) -> None:
        self._stops = self._reach.watching(lambda: self.shows(self._rows(), self._said))

    def on_unmount(self) -> None:
        self._stops()

    def nothing(self) -> str:
        return (
            ""
            if self._rows_now
            else f"[$text-muted]{t('No environment is open here yet.')}[/]"
        )

    def chosen(self, row: str) -> None:
        env = next((one for one in self._reach.envs() if one.get("id") == row), None)
        if env is not None:
            desk = Desk(env, self._reach)
            opens_page(self._host, desk, default_panel(env))


def about(env: Mapping[str, Any]) -> str:
    """What one environment is, in a line: backend, provider, workdir, facts, and closed."""
    facts = cast("dict[str, Any]", env.get("facts") or {})
    sized = [
        t(what, n=facts[key], size=facts[key])
        for key, what in (
            ("cpu", "{n} CPUs"),
            ("memory", "{size} memory"),
            ("gpu_count", "{n} GPUs"),
        )
        if facts.get(key)
    ]
    return _DOT.join(
        str(one)
        for one in (
            env.get("backend"),
            env.get("provider"),
            env.get("workdir"),
            *sized,
            *(() if env.get("open", True) else (t("closed"),)),
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
        return f"{self._desk.named} · {t(title)}"

    def page_keys(self) -> list[Key]:
        """`tab`, where there is another page to step to."""
        return (
            [Key("tab", t("Next page"))] if len(panels_of(self._desk.env)) > 1 else []
        )

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

    SEARCHES: ClassVar = False

    def __init__(self, alive: Sequence[Mapping[str, Any]]) -> None:
        super().__init__()
        self.asked = t("Terminals")
        self.about = t(
            "Come back to a terminal left running in this environment, or open a new "
            "one."
        )
        self._rows_now = [
            _Row(
                _NEW,
                t("New terminal"),
                t("a new login shell of its own in this environment"),
            ),
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
            self._wrong = t("This needs an answer.")
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

    def __init__(self, asked: str, about: str = "", doing: str = "") -> None:
        """Asks.

        Args:
          asked: The question.
          about: What doing it does.
          doing: What the button that does it says, or "" for the page's Yes.
        """
        super().__init__()
        self.asked = escape(asked)
        self.about = escape(about)
        self._doing = doing or t("Yes")

    def rows(self) -> list[tuple[str, str, str]]:
        return [
            ("yes", self._doing, t("does what was asked")),
            ("no", t("Cancel"), t("changes nothing")),
        ]


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
        self.asked = t(
            "{name} changed in the environment since you opened it.", name=escape(path)
        )
        self.about = t("Something else wrote this file on disk since you read it.")

    def rows(self) -> list[tuple[str, str, str]]:
        return [
            (
                RELOAD,
                t("Reload"),
                t("throws away your edit and reads the file again"),
            ),
            (KEEP, t("Keep mine"), t("writes your edit over what is on disk")),
            (
                COMPARE,
                t("Show the diff"),
                t("compares what is on disk with your edit"),
            ),
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

    def __init__(self, title: str, diff: str, said: str = "") -> None:
        """Shows one diff.

        Args:
          title: What it is of.
          diff: The unified diff.
          said: What is said in place of a diff that is empty, or "" for the page's own.
        """
        super().__init__()
        self._title = title
        self._diff = diff
        self._said = said or t("An empty diff.")

    def compose(self) -> ComposeResult:
        yield Label(escape(self._title), id="title")
        with VerticalScroll(id="diff"):
            yield Static(
                Syntax(self._diff, "diff", word_wrap=False)
                if self._diff
                else escape(self._said),
                id="body",
            )
        yield Label(f"[b $primary]esc[/] {t('Back')}", id="keys")


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
            Key("enter", t("Open")),
            Key("backspace", t("Up")),
            Key("n", t("New file")),
            Key("N", t("New folder")),
            Key("r", t("Rename")),
            Key("d", t("Delete")),
            Key("e", t("External editor")),
            Key("ctrl+p", t("Go to file")),
            Key("?", t("Search in files")),
            *self.page_keys(),
            Key("esc", t("Back")),
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
        entries = _entries(said)
        self._entries = {str(one.get("name")): one for one in entries}
        rows: list[_Row] = []
        for one in entries:
            label, line = _entry(one)
            rows.append(_Row(str(one.get("name")), label, line or t("Folder").lower()))
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
        return "" if self._rows_now else f"[$text-muted]{t('Nothing here yet')}[/]"

    def _at(self, name: str) -> str:
        return posixpath.join(self._path, name)

    def _edits(self, path: str, line: int = 0) -> None:
        """Opens one file in the editor; one it will not open is said under the list."""
        entry = self._entries.get(posixpath.basename(path), {})
        if (
            posixpath.dirname(path) == self._path
            and int(entry.get("size") or 0) > LARGE
        ):
            self.fails(
                _too_large(posixpath.basename(path), int(entry.get("size") or 0))
            )
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
        named = await self._interface().push_screen_wait(
            Named(
                t("New folder") if folder else t("New file"),
                t("Folder name") if folder else t("File name"),
                self._path,
            )
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
            Named(t("New name for {name}", name=row), t("New name"), "", row)
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
        sure = await self._interface().push_screen_wait(_removing(row, folder=folder))
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
            Named(t("Search in files"), t("Search"), self._desk.named)
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

    def __init__(self, paths: Sequence[str], *, truncated: bool = False) -> None:
        super().__init__()
        self.asked = t("Go to file")
        self.about = (
            t("{n} files, and more not shown", n=len(paths))
            if truncated
            else t("{n} files", n=len(paths))
        )
        self._rows_now = [_Row(one, one) for one in paths]

    def on_mount(self) -> None:
        # After the sheet's own, which puts the focus on the list.
        self.call_after_refresh(self.action_search)


class Matches(_Listing):
    """Every line a search found, to open a file at one."""

    def __init__(
        self,
        query: str,
        matches: Sequence[Mapping[str, Any]],
        *,
        truncated: bool = False,
    ) -> None:
        super().__init__()
        self.asked = t("Search in files")
        self.about = (
            t(
                "{n} lines with {query}, and more not shown",
                n=len(matches),
                query=repr(query),
            )
            if truncated
            else t("{n} lines with {query}", n=len(matches), query=repr(query))
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
        return "" if self._rows_now else f"[$text-muted]{t('No results.')}[/]"


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
                    Diff(
                        t("{path} · on disk and your edit", path=path),
                        unified(now.data, after, path),
                    )
                )
                continue
            say(
                t("{path}: kept what is on disk and dropped your edit", path=path),
                "dim",
            )
            return
        say(f"saved {path} in {desk.named}", "dim")
        return


#: What opens a file the editor here does not, said after why it does not.
_OUTSIDE = "Press e to open it in your own editor."


def _too_large(name: str, size: int) -> str:
    """That a file is too large for the editor here, and what opens it instead."""
    said = t(
        "{name} is {size}; files over {limit} are not opened here.",
        name=name,
        size=_sized(size),
        limit=_sized(LARGE),
    )
    return f"{said} {t(_OUTSIDE)}"


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
        self._state = t("Reading…")
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
            self.dismiss(_too_large(named, read.size))
            return
        try:
            if b"\0" in read.data[:8192]:
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "a NUL")  # noqa: TRY301
            text = read.data.decode("utf-8")
        except UnicodeDecodeError:
            self.dismiss(
                t("{name} is not text and cannot be opened here.", name=named)
                + f" {t(_OUTSIDE)}"
            )
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
        state = self._state or (f"● {t('Unsaved')}" if dirty else "")
        self.query_one("#status", Static).update(
            f"[b]{escape(self._path)}[/]  "
            + t("Ln {line}, Col {column}", line=row + 1, column=column + 1)
            + (f"  [$text-muted]{escape(state)}[/]" if state else "")
            + f"   [$text-muted]ctrl+s {t('Save')}{_DOT}esc {t('Close')}[/]"
        )

    @on(TextArea.SelectionChanged, "#code")
    def _moved(self) -> None:
        self._says()

    @on(TextArea.Changed, "#code")
    def _edited(self) -> None:
        if not self._loaded:
            return
        if self._state in (t("Saved"), ""):
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
            self._state = t("Saving…")
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
                    self._state = t("Conflict")
                    self._says()
                    self.run_worker(self._resolves(), group="conflict", exclusive=True)
                else:
                    self._state = t("Not saved: {why}", why=why)
                    self._says()
                return False
            self._etag = str(said.get("etag") or "")
            self._saved = text
            self._conflict = False
            self._state = t("Saved")
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
                        t("{path} · on disk and your edit", path=self._path),
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
                t(
                    "{name} has edits not written to the environment. Close and lose "
                    "them?",
                    name=posixpath.basename(self._path),
                ),
                self._state,
                t("Close"),
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
                t("Message"),
                t("Commit message"),
                needed=not self._typed_in.get("message", "").strip(),
            ),
            Question(
                "amend",
                t("Amend"),
                t("amend the commit checked out instead of adding a new one"),
                kind="steps",
            ),
        ]

    def choices(self, held: str) -> Sequence[str]:
        return ("off", "on") if held == "amend" else ()

    def lines(self, held: str) -> bool:
        return held == "message"

    def done_about(self) -> str:
        return t("commit what is staged")

    def _ask(self) -> None:
        self.query_one("#asked", Label).update(t("Commit"))
        self.query_one("#about", Label).update("")
        self._fill()

    def action_done(self) -> None:
        said = self._typed_in.get("message", "").strip()
        amend = self._typed_in.get("amend") == "on"
        if not said:
            self._wrong = t("Write a commit message first.")
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
        self.asked = f"{desk.named}: {t('Changes')}"
        self._stops: Callable[[], None] = lambda: None
        self._files: list[Mapping[str, Any]] = []

    def crumb(self) -> str:
        return t("Changes")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in self._OWN:
            return not self.typing() and not self._editing
        return super().check_action(action, parameters)

    def keys(self) -> list[Key]:
        return [
            Key("enter", t("Show the diff")),
            Key("s", t("Stage Changes")),
            Key("u", t("Unstage Changes")),
            Key("x", t("Discard Changes")),
            Key("c", t("Commit")),
            Key("r", t("Refresh")),
            *self.page_keys(),
            Key("esc", t("Back")),
        ]

    def actions(self) -> list[Action]:
        return [
            Action(
                "stage-all",
                t("Stage All Changes"),
                t("stage every change"),
                self._stages_all,
            ),
            Action(
                "unstage-all",
                t("Unstage All Changes"),
                t("unstage everything staged"),
                self._unstages_all,
            ),
            Action(
                "commit",
                t("Commit"),
                t("commit what is staged"),
                self.action_commit,
            ),
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
        self.about = _standing(said)
        self.shows(_changed(self._files))

    def nothing(self) -> str:
        return "" if self._rows_now else f"[$text-muted]{t('No changes')}[/]"

    def _under(self) -> tuple[str, str]:
        group, _, path = self.under().partition(_SEP)
        return group, path

    def chosen(self, row: str) -> None:
        group, _, path = row.partition(_SEP)
        if path:
            self.run_worker(self._diffs(path, staged=group == _STAGED), group="do")

    async def _diffs(self, path: str, *, staged: bool) -> None:
        try:
            read = await _differed(self._desk, path, staged=staged)
        except Exception as why:  # noqa: BLE001 -- said under the list
            self.fails(why)
            return
        await self._interface().push_screen_wait(Diff(read.title, read.diff, read.said))

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
            self.run_worker(
                self._does("env.git.unstage", paths=_staged(self._files, path)),
                group="do",
            )

    def action_discard(self) -> None:
        group, path = self._under()
        if path and group != _STAGED:
            self.run_worker(
                self._discards(path, untracked=group == "Untracked"), group="do"
            )

    async def _discards(self, path: str, *, untracked: bool) -> None:
        sure = await self._interface().push_screen_wait(
            _discarding(path, untracked=untracked)
        )
        if sure == "yes":
            await self._does("env.git.discard", paths=[path])

    def _stages_all(self) -> None:
        paths = _unstaged(self._files)
        if paths:
            self.run_worker(self._does("env.git.stage", paths=paths), group="do")

    def _unstages_all(self) -> None:
        paths = _staged(self._files)
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
        self.asked = f"{desk.named}: {t('Snapshots')}"
        self.about = t(
            "Rewinding puts the environment's files back as they were at that snapshot."
        )

    def keys(self) -> list[Key]:
        return [
            Key("enter", t("Rewind")),
            *self.page_keys(),
            Key("esc", t("Back")),
        ]

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
        return "" if self._rows_now else f"[$text-muted]{t('No snapshots yet.')}[/]"

    def chosen(self, row: str) -> None:
        self.run_worker(self._rewinds(row), group="do")

    async def _rewinds(self, ref: str) -> None:
        sure = await self._interface().push_screen_wait(_rewinding(ref))
        if sure != "yes":
            return
        try:
            await self._desk.asks("env.git.rewind", ref=ref)
        except Exception as why:  # noqa: BLE001 -- the guard's refusal, said
            self.fails(why)
            return
        self._said = ""
        self._desk.reach.say(t("Rewound the environment to {ref}.", ref=ref), "dim")
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
        return t(
            "/env {name}: no such environment here; choose {roles}.",
            name=named,
            roles=", ".join(roles),
        )
    host.push_screen(Envs(reach, host))
    if env is not None:
        opens_page(host, Desk(env, reach), default_panel(env))
    return ""


# -- Panes --------------------------------------------------------------------------------------

#: How long a pane waits, after being told an environment may have changed, before it reads
#: it again: a turn that writes ten files is read once, in seconds.
_SETTLE = 0.3

#: What every character that would move a terminal's cursor is drawn as in a file read here.
_PLAIN = dict.fromkeys((*range(9), 11, 12, *range(14, 32), 127), "·") | {13: None}

#: How many rows of a file are left above the line it is opened at.
_ABOVE = 3

#: What is between one key and the next on the line of a pane's keys.
_GAP = "   "

#: The folder that is open, in a tree; one that is shut is `humanfia.POINT`.
_OPEN = "▾"


def _keyed(key: str) -> str:
    """A key as it is written for a person, as the hint line writes it: `ctrl+p` is `^P`."""
    held, _, name = key.rpartition("+")
    name = name.upper() if len(name) == 1 and held else name
    return f"^{name}" if held == "ctrl" else f"{held}+{name}" if held else name


class Pane(Vertical):
    """One page of an environment as a pane beside the log: the environment's, whichever.

    The pane shows the environment its chat or epic was last turned to that has this page,
    else the first that does; with several, a first row names the one shown and `tab` turns
    to the next, for every pane of that chat or epic. It reads the environment again when
    the host says it may have changed, and says its own keys on a line at its foot.
    """

    #: Which page this is: one of :data:`PANELS`.
    PAGE: ClassVar[str] = ""
    #: What is said where environments are open and none has this page.
    NONE: ClassVar[str] = ""

    DEFAULT_CSS = """
    Pane { height: 1fr; }
    Pane > #pane-env { display: none; height: 1; padding: 0 1; color: $text-muted; }
    Pane > #pane-env.several { display: block; }
    Pane > #pane-about { height: auto; padding: 0 1; color: $text-muted; }
    Pane > #pane-list { height: 1fr; border: none; padding: 0 1; background: $surface; }
    Pane > #pane-path { height: auto; padding: 0 1; text-style: bold; }
    Pane > #pane-view { height: 1fr; padding: 0 1; }
    Pane > #pane-view:focus { background: $boost; }
    Pane > #pane-said { height: auto; padding: 0 1; color: $text-muted; }
    Pane > #pane-foot { height: auto; padding: 0 1; color: $text-muted;
        border-top: heavy $hmz-line; }
    """
    BINDINGS: ClassVar = [
        Binding("ctrl+w", "widen", "Widen", show=False),
        Binding("tab", "turn", "Next environment", show=False),
    ]

    def __init__(self, reach: Reach, host: App[Any]) -> None:
        """Makes the pane.

        Args:
          reach: The host, which says what the environments are.
          host: The interface, which the boxes and the editor open over.
        """
        super().__init__()
        self._reach = reach
        self._host = host
        self._desk: Desk | None = None
        #: What went wrong last, said over the keys until something else is.
        self._said = ""
        self._stops: Callable[[], None] = lambda: None
        self._again: Timer | None = None

    @property
    def desk(self) -> Desk | None:
        """The environment shown, or None where there is none to show."""
        return self._desk

    def compose(self) -> ComposeResult:
        """The environment shown, what the page is, what went wrong, and the keys."""
        yield Static(id="pane-env")
        yield from self.body()
        yield Static(id="pane-said")
        yield Static(id="pane-foot")

    def body(self) -> ComposeResult:
        """What this page is made of, between the environment's row and the keys."""
        yield OptionList(id="pane-list")

    def keys(self) -> list[tuple[str, str]]:
        """The keys this pane takes where the keys are now, each with what it does."""
        several = len(self._reach.desks(self.PAGE)) > 1
        return [
            *((("tab", "Next environment"),) if several else ()),
            ("ctrl+w", "Widen"),
        ]

    def nothing(self) -> str:
        """What is said while nothing went wrong, as plain text: that the page is empty."""
        return ""

    def opened(self) -> None:
        """Reads the environment now shown from the start: another one, or the first."""

    def freshens(self) -> None:
        """Reads the environment shown again, since it may have changed."""

    def aim(self) -> Widget:
        """What the keys go to when the pane is given them."""
        return self.query_one("#pane-list")

    def focus(self, scroll_visible: bool = True) -> Self:  # noqa: FBT001, FBT002
        """Gives the keys to what in the pane takes them."""
        self.aim().focus(scroll_visible)
        return self

    def on_mount(self) -> None:
        """Shows the environment, and watches for it changing."""
        self._stops = self._reach.watching(self._moved)
        self._settles()

    def on_unmount(self) -> None:
        """Stops watching."""
        self._stops()

    def on_descendant_focus(self, _: events.DescendantFocus) -> None:
        """Says the keys of whatever in the pane has them now."""
        self.draws()

    def on_descendant_blur(self, _: events.DescendantBlur) -> None:
        """Says them again once the keys have settled somewhere."""
        self.call_after_refresh(self.draws)

    def _moved(self) -> None:
        if self._again is not None:
            self._again.stop()
        self._again = self.set_timer(_SETTLE, self._settled)

    def _settled(self) -> None:
        was = self._desk.id if self._desk is not None else None
        self._settles()
        if self._desk is not None and self._desk.id == was:
            self.freshens()

    def _settles(self) -> None:
        """Turns to the environment to show, reading it from the start where it is another."""
        desks = self._reach.desks(self.PAGE)
        desk = self._reach.desk(self.PAGE)
        was = self._desk
        self._desk = desk
        row = self.query_one("#pane-env", Static)
        row.set_class(len(desks) > 1, "several")
        if desk is not None:
            at = next(at for at, one in enumerate(desks, 1) if one.id == desk.id)
            row.update(
                f"{t('Environment')} [b $primary]{escape(desk.named)}[/]"
                f"  {at}/{len(desks)}"
            )
        if (was.id if was is not None else None) != (
            desk.id if desk is not None else None
        ) or (was is None and desk is None):
            self._said = ""
            self.opened()
        self.draws()

    def draws(self) -> None:
        """Draws what is said over the keys, and the keys."""
        if not self.is_mounted:
            return
        if self._said:
            said = f"[$error]{escape(self._said)}[/]"
        elif self._desk is None:
            said = escape(
                t(self.NONE)
                if self._reach.envs()
                else t("No environment is open here yet.")
            )
        else:
            said = escape(self.nothing())
        line = self.query_one("#pane-said", Static)
        line.display = bool(said)
        line.update(said)
        # A row at a time, so that a key is never at the end of one row and what it does at
        # the start of the next.
        room = max(self.size.width - 2, 1)
        rows: list[list[str]] = [[]]
        used = 0
        for key, does in self.keys():
            shown, doing = _keyed(key), t(does)
            wide = len(shown) + 1 + len(doing)
            if rows[-1] and used + len(_GAP) + wide > room:
                rows.append([])
                used = 0
            used += wide + (len(_GAP) if rows[-1] else 0)
            rows[-1].append(f"[b $primary]{escape(shown)}[/] {escape(doing)}")
        self.query_one("#pane-foot", Static).update(
            "\n".join(_GAP.join(row) for row in rows)
        )

    def on_resize(self, _: events.Resize) -> None:
        """Lays the keys out again in however wide the pane is now."""
        self.draws()

    def fails(self, why: BaseException | str) -> None:
        """Says what went wrong, over the keys."""
        self._said = str(why)
        self.draws()

    def says(self, said: str = "") -> None:
        """Says something over the keys, or takes back what was said."""
        self._said = said
        self.draws()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Leaves `tab` to the interface where there is one environment only."""
        if action == "turn":
            return len(self._reach.desks(self.PAGE)) > 1
        return super().check_action(action, parameters)

    def action_widen(self) -> None:
        """Makes the zone the pane is in one step wider."""
        for one in self.ancestors:
            if isinstance(one, Zone):
                one.widens()
                return

    def action_turn(self) -> None:
        """Turns every pane of this chat or epic to the next environment that has this page."""
        desks = self._reach.desks(self.PAGE)
        if len(desks) < 2 or self._desk is None:  # noqa: PLR2004 -- one to turn to
            return
        ids = [one.id for one in desks]
        at = ids.index(self._desk.id) if self._desk.id in ids else -1
        self._reach.turns(ids[(at + 1) % len(ids)])
        self._settles()

    def _gone(self, desk: Desk) -> bool:
        """Whether the pane has turned from an environment since something was asked of it."""
        return self._desk is None or self._desk.id != desk.id

    def _under(self) -> str:
        """The row of the list under the cursor, by its id, or ""."""
        listing = self.query_one("#pane-list", OptionList)
        if listing.highlighted is None:
            return ""
        return str(listing.get_option_at_index(listing.highlighted).id or "")

    def _lists(self, options: Sequence[Option], landing: str = "") -> None:
        """Puts rows in the list, the cursor on `landing` or where it was, else the first."""
        listing = self.query_one("#pane-list", OptionList)
        was = landing or self._under()
        listing.set_options(options)
        at = next(
            (
                at
                for at, one in enumerate(options)
                if one.id == was and not one.disabled
            ),
            next((at for at, one in enumerate(options) if not one.disabled), None),
        )
        listing.highlighted = at

    def _shade(self) -> str:
        """The colours code is read in: the terminal's own sixteen, light or dark."""
        return "ansi_dark" if self._host.current_theme.dark else "ansi_light"


class FilesPane(Pane):
    """An environment's files as a tree beside the log, and one of them to read."""

    PAGE: ClassVar = "files"
    NONE: ClassVar = "No files in this environment"

    DEFAULT_CSS = """
    FilesPane > #pane-path { display: none; }
    FilesPane > #pane-view { display: none; }
    FilesPane.reading > #pane-list { display: none; }
    FilesPane.reading > #pane-path { display: block; }
    FilesPane.reading > #pane-view { display: block; }
    """
    BINDINGS: ClassVar = [
        Binding("e", "edit", "Edit", show=False),
        Binding("n", "new_file", "New file", show=False),
        Binding("N", "new_folder", "New folder", show=False),
        Binding("r", "rename", "Rename", show=False),
        Binding("d", "delete", "Delete", show=False),
        Binding("ctrl+p", "quick", "Go to file", show=False),
        Binding("slash", "find", "Search in files", show=False),
        Binding("backspace", "back", "Back", show=False),
    ]

    #: The keys of the tree, which do nothing while a file is being read.
    _TREE = frozenset({"new_file", "new_folder", "rename", "delete"})

    def __init__(self, reach: Reach, host: App[Any]) -> None:
        """Makes the pane.

        Args:
          reach: The host.
          host: The interface.
        """
        super().__init__(reach, host)
        self._root = ""
        #: Each directory read, by its path: its entries, folders first.
        self._kids: dict[str, list[Mapping[str, Any]]] = {}
        #: What each path listed is: `dir`, `file` or `link`.
        self._kinds: dict[str, str] = {}
        #: The folders open in the tree.
        self._unfolded: set[str] = set()
        #: The file being read, or "", and what it was when it was drawn.
        self._reading: str = ""
        self._drawn: str = ""

    @property
    def reading(self) -> str:
        """The file being read in the pane, by its path, or "" while the tree is shown."""
        return self._reading

    def body(self) -> ComposeResult:
        """The tree, and over it once a file is opened, the file."""
        yield OptionList(id="pane-list")
        yield Static(id="pane-path")
        with VerticalScroll(id="pane-view"):
            yield Static(id="pane-text")

    def keys(self) -> list[tuple[str, str]]:
        """The tree's keys, or those of the file being read."""
        if self._reading:
            return [
                ("backspace", "Back"),
                ("e", "Edit"),
                ("ctrl+p", "Go to file"),
                ("/", "Search in files"),
                *super().keys(),
            ]
        return [
            ("enter", "Open"),
            ("e", "Edit"),
            ("n", "New file"),
            ("shift+n", "New folder"),
            ("r", "Rename"),
            ("d", "Delete"),
            ("ctrl+p", "Go to file"),
            ("/", "Search in files"),
            *super().keys(),
        ]

    def nothing(self) -> str:
        """That the environment's directory is empty, once it has been read and is."""
        empty = self._root in self._kids and not self._kids[self._root]
        return t("Nothing here yet") if empty and not self._reading else ""

    def aim(self) -> Widget:
        """The file where one is being read, else the tree."""
        return self.query_one("#pane-view" if self._reading else "#pane-list")

    def opened(self) -> None:
        """Forgets the tree, and reads the top of the environment now shown."""
        self._kids, self._kinds, self._unfolded = {}, {}, set()
        self._shuts()
        self._root = self._desk.workdir if self._desk is not None else ""
        self._trees()
        if self._desk is not None:
            self.run_worker(self._reads([self._root]), group="list", exclusive=True)

    def freshens(self) -> None:
        """Reads every folder open again, and the file being read."""
        folders = [self._root, *sorted(self._unfolded)]
        self.run_worker(self._reads(folders), group="list", exclusive=True)
        if self._reading:
            self.run_worker(
                self._shows(self._reading, quiet=True), group="view", exclusive=True
            )

    async def _reads(self, folders: Sequence[str], landing: str = "") -> None:
        """Reads directories off the host, and draws the tree with what they hold."""
        desk = self._desk
        if desk is None:
            return
        read = await asyncio.gather(
            *(desk.asks("env.list", path=folder) for folder in folders),
            return_exceptions=True,
        )
        if self._gone(desk):
            return
        for folder, said in zip(folders, read, strict=True):
            if isinstance(said, BaseException):
                if folder == self._root:
                    self.fails(said)
                    return
                # A folder gone since it was opened: shut, and nothing said of it.
                self._unfolded.discard(folder)
                self._kids.pop(folder, None)
                continue
            at = folder
            if folder == self._root:
                at = self._root = str(said.get("path") or folder)
            self._kids[at] = _entries(said)
            for one in self._kids[at]:
                path = posixpath.join(at, str(one.get("name")))
                kind = str(one.get("kind") or "file")
                # A link opened as the folder it leads to is still that, read again.
                if not (kind == "link" and path in self._unfolded):
                    self._kinds[path] = kind
        self._trees(landing)
        self.draws()

    def _trees(self, landing: str = "") -> None:
        """Draws the tree: each folder open with what it holds under it, a step in."""
        options: list[Option] = []

        def lays(folder: str, depth: int) -> None:
            for one in self._kids.get(folder, ()):
                label, line = _entry(one)
                path = posixpath.join(folder, str(one.get("name")))
                pad = "  " * depth
                if self._kinds.get(path) == "dir":
                    shut = path not in self._unfolded
                    mark = humanfia.POINT if shut else _OPEN
                    options.append(
                        Option(f"{pad}[$text-muted]{mark}[/] {escape(label)}", id=path)
                    )
                    if not shut:
                        lays(path, depth + 1)
                else:
                    options.append(
                        Option(
                            f"{pad}  {escape(label)}  [$text-muted]{escape(line)}[/]",
                            id=path,
                        )
                    )

        lays(self._root, 0)
        self._lists(options, landing)

    @on(OptionList.OptionSelected, "#pane-list")
    def _picked(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        path = str(event.option.id or "")
        kind = self._kinds.get(path)
        if kind == "dir":
            self._folds(path)
        elif kind == "link":
            self.run_worker(self._follows(path), group="list", exclusive=True)
        elif path:
            self.shows(path)

    def _folds(self, path: str) -> None:
        """Opens a folder of the tree, reading it, or shuts one that is open."""
        if path in self._unfolded:
            self._unfolded.discard(path)
            self._trees()
        else:
            self._unfolded.add(path)
            self.run_worker(self._reads([path]), group="list", exclusive=True)

    async def _follows(self, path: str) -> None:
        """Opens a link: as a folder where it leads to one, as a file where it does not."""
        desk = self._desk
        if desk is None:
            return
        try:
            await desk.asks("env.list", path=path)
        except Exception:  # noqa: BLE001 -- not a directory, so a file to read
            await self._shows(path)
            return
        self._kinds[path] = "dir"
        self._unfolded.add(path)
        await self._reads([path])

    def shows(self, path: str, line: int = 0) -> None:
        """Opens one file to read in the pane, in place of the tree.

        Args:
          path: The file.
          line: The line to show, from 1, or 0 for the top.
        """
        self.run_worker(self._shows(path, line), group="view", exclusive=True)

    async def _shows(self, path: str, line: int = 0, *, quiet: bool = False) -> None:
        """Reads one file and draws it, coloured by its name; `quiet` reads one again."""
        desk = self._desk
        if desk is None:
            return
        name = posixpath.basename(path)
        try:
            read = await _read(desk, path, cap=VIEWED)
        except Exception as why:  # noqa: BLE001 -- said over the keys
            if quiet:
                # Gone since it was opened: back to the tree, which no longer lists it.
                self._shuts()
            self.fails(why)
            return
        if self._gone(desk):
            return
        if not read.whole:
            self.fails(
                t(
                    "{name} is {size}; files over {limit} are not opened here.",
                    name=name,
                    size=_sized(read.size),
                    limit=_sized(VIEWED),
                )
            )
            return
        if quiet and path == self._reading and read.etag == self._drawn:
            return
        said = ""
        try:
            if b"\0" in read.data[:8192]:
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "a NUL")  # noqa: TRY301
            text = read.data.decode("utf-8")
        except UnicodeDecodeError:
            text = read.data.decode("utf-8", "replace")
            said = t("{name} is not UTF-8 text, so it is open read-only.", name=name)
        text = text.translate(_PLAIN)
        within = self.has_focus_within
        self._reading, self._drawn = path, read.etag
        self.add_class("reading")
        shown = posixpath.relpath(path, self._root) if self._root else path
        self.query_one("#pane-path", Static).update(escape(shown))
        self.query_one("#pane-text", Static).update(
            Syntax(
                text,
                Syntax.guess_lexer(path, code=text),
                theme=self._shade(),
                line_numbers=True,
                word_wrap=True,
                highlight_lines={line} if line else None,
            )
        )
        if not quiet:
            self._said = said
            view = self.query_one("#pane-view", VerticalScroll)
            if within:
                view.focus()
            view.scroll_to(y=self._row_of(text, line, view), animate=False)
        self.draws()

    @staticmethod
    def _row_of(text: str, line: int, view: VerticalScroll) -> int:
        """The row a line of a file is drawn on, less a few, counting the rows lines wrap to."""
        if line <= 1:
            return 0
        lines = text.split("\n")
        # What is left of the pane's width for code, beside the numbers and their margin.
        room = max(view.size.width - 2 - len(str(len(lines))) - 3, 1)
        rows = sum(max(-(-cell_len(one) // room), 1) for one in lines[: line - 1])
        return max(rows - _ABOVE, 0)

    def _shuts(self) -> None:
        """Puts the tree back in place of the file being read."""
        within = self.is_mounted and self.has_focus_within
        self._reading = self._drawn = ""
        self.remove_class("reading")
        if within:
            self.query_one("#pane-list").focus()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Leaves the tree's keys alone while a file is read, and `backspace` while not."""
        if action in self._TREE:
            return not self._reading
        if action == "back":
            return bool(self._reading)
        return super().check_action(action, parameters)

    def action_back(self) -> None:
        """Back from the file to the tree."""
        self._shuts()
        self.says()

    def _picked_file(self) -> str:
        """The file `e` means: the one being read, else the one under the cursor."""
        if self._reading:
            return self._reading
        path = self._under()
        return path if path and self._kinds.get(path) != "dir" else ""

    def action_edit(self) -> None:
        """Opens the file in the editor, which saves itself, over the screen."""
        if (path := self._picked_file()) and self._desk is not None:
            self._edits(path)

    def _edits(self, path: str, line: int = 0) -> None:
        if self._desk is None:
            return

        def closed(why: str | None) -> None:
            if why:
                self.fails(why)
            self.freshens()

        self._host.push_screen(Editing(self._desk, path, self._host, line=line), closed)

    def _folder(self) -> str:
        """Where a new file goes: the open folder under the cursor, else beside the row."""
        path = self._under()
        if not path:
            return self._root
        if self._kinds.get(path) == "dir" and path in self._unfolded:
            return path
        return posixpath.dirname(path)

    def action_new_file(self) -> None:
        """Asks for a name, makes an empty file of it, and opens it in the editor."""
        self.run_worker(self._makes(folder=False), group="do")

    def action_new_folder(self) -> None:
        """Asks for a name, and makes a folder of it."""
        self.run_worker(self._makes(folder=True), group="do")

    def action_rename(self) -> None:
        """Asks what the row under the cursor is called now."""
        if path := self._under():
            self.run_worker(self._renames(path), group="do")

    def action_delete(self) -> None:
        """Deletes the row under the cursor, once a box has asked."""
        if path := self._under():
            self.run_worker(self._removes(path), group="do")

    def action_quick(self) -> None:
        """Opens a file by its name, narrowed by typing."""
        self.run_worker(self._quick(), group="do")

    def action_find(self) -> None:
        """Searches the environment's files for a text, and opens a file at a line found."""
        self.run_worker(self._finds(), group="do")

    async def _makes(self, *, folder: bool) -> None:
        desk, within = self._desk, self._folder()
        if desk is None:
            return
        named = await self._host.push_screen_wait(
            Named(
                t("New folder") if folder else t("New file"),
                t("Folder name") if folder else t("File name"),
                within,
            )
        )
        if not named:
            return
        path = posixpath.join(within, named)
        try:
            if folder:
                await desk.asks("env.mkdir", path=path)
            else:
                await desk.asks("env.write", path=path, data="", if_match="")
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        self._said = ""
        await self._reads([within], landing=posixpath.join(within, named.split("/")[0]))
        if not folder:
            self._edits(path)

    async def _renames(self, path: str) -> None:
        desk, was = self._desk, posixpath.basename(path)
        if desk is None:
            return
        named = await self._host.push_screen_wait(
            Named(t("New name for {name}", name=was), t("New name"), "", was)
        )
        if not named or named == was:
            return
        to = posixpath.join(posixpath.dirname(path), named)
        try:
            await desk.asks("env.rename", path=path, to=to)
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        self._said = ""
        if path in self._unfolded:
            self._unfolded.discard(path)
        await self._reads([posixpath.dirname(path)], landing=to)

    async def _removes(self, path: str) -> None:
        desk = self._desk
        if desk is None:
            return
        folder = self._kinds.get(path) == "dir"
        sure = await self._host.push_screen_wait(
            _removing(posixpath.basename(path), folder=folder)
        )
        if sure != "yes":
            return
        try:
            await desk.asks("env.remove", path=path)
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        self._said = ""
        self._unfolded = {
            one
            for one in self._unfolded
            if one != path and not one.startswith(f"{path}/")
        }
        await self._reads([posixpath.dirname(path)])

    def _whole(self, path: str) -> str:
        """A path the host named, from the top: one given from where the environment works."""
        return path if path.startswith("/") else posixpath.join(self._root, path)

    async def _quick(self) -> None:
        desk = self._desk
        if desk is None:
            return
        try:
            found = await desk.asks("env.find")
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        picked = await self._host.push_screen_wait(
            Opens(
                [str(one) for one in found.get("paths") or ()],
                truncated=bool(found.get("truncated")),
            )
        )
        if picked:
            await self._shows(self._whole(picked))

    async def _finds(self) -> None:
        desk = self._desk
        if desk is None:
            return
        query = await self._host.push_screen_wait(
            Named(t("Search in files"), t("Search"), desk.named)
        )
        if not query:
            return
        try:
            found = await desk.asks("env.search", query=query)
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        picked = await self._host.push_screen_wait(
            Matches(
                query,
                list(found.get("matches") or ()),
                truncated=bool(found.get("truncated")),
            )
        )
        if picked:
            path, _, line = picked.rpartition(_SEP)
            await self._shows(self._whole(path), int(line or 0))


class ChangesPane(Pane):
    """An environment's git changes beside the log: the list, and the change of one file."""

    PAGE: ClassVar = "changes"
    NONE: ClassVar = "No changes in this environment"

    DEFAULT_CSS = """
    ChangesPane > #pane-list { height: auto; max-height: 40%; }
    ChangesPane > #pane-path { border-top: heavy $hmz-line; color: $text-muted; }
    ChangesPane.listing > #pane-list { height: 1fr; max-height: 100%; }
    ChangesPane.listing > #pane-path { display: none; }
    ChangesPane.listing > #pane-view { display: none; }
    """
    BINDINGS: ClassVar = [
        Binding("s", "stage", "Stage Changes", show=False),
        Binding("u", "unstage", "Unstage Changes", show=False),
        Binding("x", "discard", "Discard Changes", show=False),
        Binding("S", "stage_all", "Stage All Changes", show=False),
        Binding("U", "unstage_all", "Unstage All Changes", show=False),
        Binding("c", "commit", "Commit", show=False),
        Binding("l", "log", "Commits", show=False),
        Binding("p", "snapshots", "Snapshots", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("backspace", "back", "Back", show=False),
    ]

    #: The keys of the list of changes, which do nothing on the commits or the snapshots.
    _STATUS = frozenset(
        {
            "stage",
            "unstage",
            "discard",
            "stage_all",
            "unstage_all",
            "commit",
            "log",
            "snapshots",
        }
    )

    def __init__(self, reach: Reach, host: App[Any]) -> None:
        """Makes the pane.

        Args:
          reach: The host.
          host: The interface.
        """
        super().__init__(reach, host)
        #: What the list is of: `status`, `log` or `snapshots`.
        self._mode = "status"
        self._files: list[Mapping[str, Any]] = []
        #: Whether the list has been read, and so may be said to be empty.
        self._read_in = False
        #: The row whose change is drawn under the list, and that row with what was drawn.
        self._diffed = ""
        self._shown: tuple[str, _Differed] | None = None

    @property
    def mode(self) -> str:
        """What the list is of now: `status`, `log` or `snapshots`."""
        return self._mode

    def body(self) -> ComposeResult:
        """Where the repository stands, the list, and under it the change of one file."""
        yield Static(id="pane-about")
        yield OptionList(id="pane-list")
        yield Static(id="pane-path")
        with VerticalScroll(id="pane-view"):
            yield Static(id="pane-text")

    def keys(self) -> list[tuple[str, str]]:
        """The keys of the list of changes, of the diff, of the commits, or of the snapshots."""
        if self._mode == "log":
            return [("backspace", "Back"), ("r", "Refresh"), *super().keys()]
        if self._mode == "snapshots":
            return [
                ("enter", "Rewind"),
                ("backspace", "Back"),
                ("r", "Refresh"),
                *super().keys(),
            ]
        if self.query_one("#pane-view").has_focus:
            return [("backspace", "Close the diff"), *super().keys()]
        return [
            ("enter", "Show the diff"),
            ("s", "Stage Changes"),
            ("u", "Unstage Changes"),
            ("x", "Discard Changes"),
            ("shift+s", "Stage All Changes"),
            ("shift+u", "Unstage All Changes"),
            ("c", "Commit"),
            ("l", "Commits"),
            ("p", "Snapshots"),
            ("r", "Refresh"),
            *super().keys(),
        ]

    def nothing(self) -> str:
        """That there is nothing to list, once the list has been read and is empty."""
        listing = self.query_one("#pane-list", OptionList)
        if not self._read_in or listing.option_count:
            return ""
        return t(
            {"log": "No commits yet.", "snapshots": "No snapshots yet."}.get(
                self._mode, "No changes"
            )
        )

    def opened(self) -> None:
        """Reads the changes of the environment now shown."""
        self._files, self._read_in = [], False
        self._turns_to("status")

    def freshens(self) -> None:
        """Reads what is listed again."""
        self.action_refresh()

    def _turns_to(self, mode: str) -> None:
        """Lists the changes, the commits or the snapshots, read from the host."""
        self._mode = mode
        self._read_in = False
        self.set_class(mode != "status", "listing")
        self._lists([])
        self._diffs_none()
        self.query_one("#pane-about", Static).update("")
        if self.has_focus_within:
            self.query_one("#pane-list").focus()
        self.action_refresh()

    def action_refresh(self) -> None:
        """Reads what is listed off the host again."""
        if self._desk is None:
            return
        reads = {"log": self._logs, "snapshots": self._snaps}.get(
            self._mode, self._reads
        )
        self.run_worker(reads(), group="status", exclusive=True)

    async def _reads(self) -> None:
        desk = self._desk
        if desk is None:
            return
        try:
            said = await desk.asks("env.git.status")
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        if self._gone(desk) or self._mode != "status":
            return
        self._files = list(said.get("files") or ())
        self.query_one("#pane-about", Static).update(escape(_standing(said)))
        options = [
            Option(f"[b $text-muted]{escape(one.label)}[/]", id=one.id, disabled=True)
            if one.heading
            else Option(
                f" {escape(one.label)}  [$text-muted]{escape(one.about)}[/]", id=one.id
            )
            for one in _changed(self._files)
        ]
        self._read_in = True
        # A change staged or unstaged is in another group now: the cursor goes with it.
        was = self._under().partition(_SEP)[2]
        moved = next(
            (
                str(one.id)
                for one in options
                if was and not one.disabled and str(one.id).endswith(f"{_SEP}{was}")
            ),
            "",
        )
        self._lists(
            options, "" if self._under() in {one.id for one in options} else moved
        )
        if not self._under():
            self._diffs_none()
        self.draws()

    async def _logs(self) -> None:
        desk = self._desk
        if desk is None:
            return
        try:
            said = await desk.asks("env.git.log")
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        if self._gone(desk) or self._mode != "log":
            return
        self.query_one("#pane-about", Static).update(t("Commits"))
        self._read_in = True
        self._lists(
            [
                Option(
                    f"[$primary]{escape(str(one.get('hash'))[:7])}[/] "
                    f"{escape(str(one.get('subject') or ''))}  [$text-muted]"
                    f"{escape(str(one.get('author') or ''))}{_DOT}"
                    f"{escape(str(one.get('date') or '')[:10])}[/]",
                    id=str(one.get("hash")),
                )
                for one in said.get("commits") or ()
            ]
        )
        self.draws()

    async def _snaps(self) -> None:
        desk = self._desk
        if desk is None:
            return
        try:
            said = await desk.asks("env.git.snapshots")
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        if self._gone(desk) or self._mode != "snapshots":
            return
        self.query_one("#pane-about", Static).update(t("Snapshots"))
        self._read_in = True
        self._lists(
            [
                Option(escape(str(one)), id=str(one))
                for one in said.get("snapshots") or ()
            ]
        )
        self.draws()

    def _row(self) -> tuple[str, str]:
        """The change under the cursor: its group and its path, or two of ""."""
        if self._mode != "status":
            return "", ""
        group, _, path = self._under().partition(_SEP)
        return group, path

    @on(OptionList.OptionHighlighted, "#pane-list")
    def _moved_to(self, event: OptionList.OptionHighlighted) -> None:
        event.stop()
        group, path = self._row()
        if not path:
            return
        self._diffed = self._under()
        self.run_worker(
            self._diffs(path, staged=group == _STAGED), group="diff", exclusive=True
        )

    def _diffs_none(self) -> None:
        """Says to pick a file, where the change of none is drawn."""
        self._diffed, self._shown = "", None
        self.query_one("#pane-path", Static).update("")
        self.query_one("#pane-text", Static).update(
            f"[$text-muted]{escape(t('Pick a file in the list to see its diff.'))}[/]"
        )

    async def _diffs(self, path: str, *, staged: bool) -> None:
        desk, row = self._desk, self._diffed
        if desk is None:
            return
        try:
            read = await _differed(desk, path, staged=staged)
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        if self._gone(desk) or row != self._diffed or self._shown == (row, read):
            return
        another = self._shown is None or self._shown[0] != row
        self._shown = row, read
        self.query_one("#pane-path", Static).update(escape(read.title))
        self.query_one("#pane-text", Static).update(
            Syntax(
                read.diff,
                "diff",
                theme=self._shade(),
                word_wrap=True,
            )
            if read.diff
            else f"[$text-muted]{escape(read.said)}[/]"
        )
        if another:
            self.query_one("#pane-view", VerticalScroll).scroll_home(animate=False)

    @on(OptionList.OptionSelected, "#pane-list")
    def _picked(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if self._mode == "snapshots":
            self.run_worker(self._rewinds(str(event.option.id or "")), group="do")
        elif self._mode == "status" and self._row()[1]:
            self.query_one("#pane-view").focus()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Leaves the keys of the changes alone on the commits and on the snapshots."""
        if action in self._STATUS:
            return self._mode == "status"
        if action == "back":
            return self._mode != "status" or self.query_one("#pane-view").has_focus
        return super().check_action(action, parameters)

    def action_back(self) -> None:
        """Back from the diff to the list, or from the commits or snapshots to the changes."""
        if self._mode == "status":
            self.query_one("#pane-list").focus()
        else:
            self.says()
            self._turns_to("status")

    def action_log(self) -> None:
        """Lists the commits, newest first."""
        self.says()
        self._turns_to("log")

    def action_snapshots(self) -> None:
        """Lists the snapshots the environment can be rewound to."""
        self.says()
        self._turns_to("snapshots")

    async def _does(self, method: str, /, **params: Any) -> None:
        desk = self._desk
        if desk is None:
            return
        try:
            await desk.asks(method, **params)
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        self._said = ""
        await self._reads()

    def action_stage(self) -> None:
        """Stages the change under the cursor."""
        group, path = self._row()
        if path and group != _STAGED:
            self.run_worker(self._does("env.git.stage", paths=[path]), group="do")

    def action_unstage(self) -> None:
        """Unstages the change under the cursor."""
        group, path = self._row()
        if path and group == _STAGED:
            self.run_worker(
                self._does("env.git.unstage", paths=_staged(self._files, path)),
                group="do",
            )

    def action_stage_all(self) -> None:
        """Stages every change."""
        if paths := _unstaged(self._files):
            self.run_worker(self._does("env.git.stage", paths=paths), group="do")

    def action_unstage_all(self) -> None:
        """Unstages everything staged."""
        if paths := _staged(self._files):
            self.run_worker(self._does("env.git.unstage", paths=paths), group="do")

    def action_discard(self) -> None:
        """Throws the change under the cursor away, once a box has asked."""
        group, path = self._row()
        if path and group != _STAGED:
            self.run_worker(
                self._discards(path, untracked=group == "Untracked"), group="do"
            )

    async def _discards(self, path: str, *, untracked: bool) -> None:
        sure = await self._host.push_screen_wait(_discarding(path, untracked=untracked))
        if sure == "yes":
            await self._does("env.git.discard", paths=[path])

    def action_commit(self) -> None:
        """Asks for a message, and commits what is staged, or amends the last commit."""
        self.run_worker(self._commits(), group="do")

    async def _commits(self) -> None:
        said = await self._host.push_screen_wait(Commit())
        if said is None:
            return
        message, amend = said
        await self._does("env.git.commit", message=message, amend=amend)

    async def _rewinds(self, ref: str) -> None:
        desk = self._desk
        if desk is None or not ref:
            return
        sure = await self._host.push_screen_wait(_rewinding(ref))
        if sure != "yes":
            return
        try:
            await desk.asks("env.git.rewind", ref=ref)
        except Exception as why:  # noqa: BLE001 -- the guard's refusal, said
            self.fails(why)
            return
        self.says()
        self._turns_to("status")


# -- The terminal in a pane ---------------------------------------------------------------------

#: What each key that is not a character is to a terminal.
_SENT = {
    "enter": "\r",
    "tab": "\t",
    "shift+tab": "\x1b[Z",
    "backspace": "\x7f",
    "escape": "\x1b",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "insert": "\x1b[2~",
    "delete": "\x1b[3~",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "f1": "\x1bOP",
    "f2": "\x1bOQ",
    "f3": "\x1bOR",
    "f4": "\x1bOS",
    "f5": "\x1b[15~",
    "f6": "\x1b[17~",
    "f7": "\x1b[18~",
    "f8": "\x1b[19~",
    "f9": "\x1b[20~",
    "f10": "\x1b[21~",
    "f11": "\x1b[23~",
    "f12": "\x1b[24~",
}

#: How many hundredths of a second a terminal waits to be laid out before it is opened.
_LAID_OUT = 100

#: The arrows and their like, which a terminal in application mode is sent differently.
_CURSOR = frozenset({"up", "down", "right", "left", "home", "end"})

#: The mode a program sets to be sent them so (DECCKM), as the emulator keeps private modes.
_APPLICATION = 1 << 5

#: The emulator's names for the colours that are not Rich's.
_HUES = {"brown": "yellow", "brightbrown": "bright_yellow"}

#: How long a colour written as its red, green and blue is.
_HEX = 6


def _hue(name: str) -> str | None:
    """One of the emulator's colours, as Rich names it; None for the terminal's own."""
    if name == "default":
        return None
    if name in _HUES:
        return _HUES[name]
    if name.startswith("bright"):
        return f"bright_{name.removeprefix('bright')}"
    if len(name) == _HEX and all(one in "0123456789abcdefABCDEF" for one in name):
        return f"#{name}"
    return name


@functools.cache
def _cell(
    fg: str,
    bg: str,
    *,
    bold: bool,
    italics: bool,
    underscore: bool,
    reverse: bool,
) -> Style:
    """The style of one cell of the emulator's screen."""
    try:
        return Style(
            color=_hue(fg),
            bgcolor=_hue(bg),
            bold=bold or None,
            italic=italics or None,
            underline=underscore or None,
            reverse=reverse or None,
        )
    except Exception:  # noqa: BLE001 -- a colour Rich has no name for: the terminal's own
        return Style(bold=bold or None, reverse=reverse or None)


class Tty(Widget, can_focus=True):
    """One terminal of an environment, drawn in a pane and typed into while it has the keys.

    What the terminal prints is read by a terminal emulator and drawn as its screen; every
    key pressed while this has the keys is the terminal's, but for `~.` after a newline,
    which gives the keys back and leaves it running, as it does in the shell `/env` hands
    the whole screen to.
    """

    DEFAULT_CSS = """
    Tty { height: 1fr; }
    """

    class Left(Message):
        """`~.` was typed: the keys are to go back to the pane."""

    class Opened(Message):
        """The terminal is open, and which it is is known."""

        def __init__(self, tty: Tty) -> None:
            """Says which.

            Args:
              tty: What draws it.
            """
            super().__init__()
            self.tty = tty

    class Ended(Message):
        """The terminal ended, or could not be opened."""

        def __init__(self, tty: Tty) -> None:
            """Says which.

            Args:
              tty: What drew it.
            """
            super().__init__()
            self.tty = tty

    def __init__(self, desk: Desk, term: str = "") -> None:
        """Draws one terminal.

        Args:
          desk: The environment.
          term: The terminal to come back to, or "" to open a new one.
        """
        super().__init__()
        self._desk = desk
        #: The terminal, or "" until a new one is open.
        self.term = term
        #: How it ended, as it is said in the pane, or "" while it runs.
        self.ended = ""
        emulator = cast("Any", pyte)
        self._screen: Any = emulator.Screen(80, 24)
        self._stream: Any = emulator.ByteStream(self._screen)
        # What a program asks the terminal -- where the cursor is -- is answered as typed.
        self._screen.write_process_input = self._answers
        self._escape = Escape()
        self._credit = Credit()
        self._typed: asyncio.Queue[bytes] = asyncio.Queue()
        #: What was told of terminals before this one was known, or None once it is.
        self._early: list[tuple[dict[str, Any], bool]] | None = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._viewing = Viewing(self._told, term)
        self._stops: Callable[[], None] = lambda: None
        #: Each row as it was drawn last, the size they were drawn at, and where the cursor was.
        self._rows: dict[int, Text] = {}
        self._sized = (0, 0)
        self._cursor: tuple[int, int] | None = None

    @property
    def text(self) -> str:
        """What the terminal's screen shows, a line to a row, as plain text."""
        return "\n".join(one.rstrip() for one in self._screen.display)

    def _cells(self) -> tuple[int, int]:
        """How many columns and rows there are to draw in."""
        return self.size.width or 80, self.size.height or 24

    def on_mount(self) -> None:
        """Watches the terminal, and opens it once there is a size to open it at."""
        self._loop = asyncio.get_running_loop()
        self._stops = self._desk.reach.views(self._viewing)
        self.call_after_refresh(
            lambda: self.run_worker(self._attaches(), group="attach", exclusive=True)
        )

    def on_unmount(self) -> None:
        """Stops watching; the terminal keeps running, and what was drawn is acknowledged."""
        self._stops()
        if self.term and (rest := self._credit.rest()):
            threading.Thread(
                target=self._acked, args=(rest,), daemon=True, name="hmz-env-ack"
            ).start()

    def _acked(self, drawn: int) -> None:
        with contextlib.suppress(Exception):
            self._desk.reach.ask("env.term.ack", {"term": self.term, "bytes": drawn})

    async def _asks(self, method: str, /, **params: Any) -> dict[str, Any]:
        """Asks the host one thing of this terminal, which is named by itself alone."""
        return await asyncio.to_thread(
            self._desk.reach.ask, method, {"term": self.term, **params}
        )

    async def _attaches(self) -> None:
        """Opens the terminal, or comes back to it, then sends on what is typed, in order."""
        # Opened at the size it is drawn at, which is known once the pane has been laid out.
        for _ in range(_LAID_OUT):
            if self.size.width and self.size.height:
                break
            await asyncio.sleep(0.01)
        cols, rows = self._cells()
        self._screen.resize(rows, cols)
        try:
            opened = await self._desk.asks(
                "env.term.open",
                cols=cols,
                rows=rows,
                **({"term": self.term} if self.term else {}),
            )
        except Exception as why:  # noqa: BLE001 -- refused, in the host's words
            self._stops()
            self._early = None
            self._ends(str(why))
            return
        self.term = self._viewing.term = str(opened.get("term") or self.term)
        self._draws(_decoded(opened.get("replay")), acked=True)
        early, self._early = self._early or [], None
        for message, acked in early:
            self._hears(message, acked)
        self.post_message(self.Opened(self))
        if self._cells() != (cols, rows):
            # Made another size while it was being opened, which nothing was told of.
            cols, rows = self._cells()
            with contextlib.suppress(Exception):
                await self._asks("env.term.resize", cols=cols, rows=rows)
        while True:
            data = await self._typed.get()
            while not self._typed.empty():
                data += self._typed.get_nowait()
            try:
                await self._asks("env.term.input", data=_encoded(data))
            except Exception as why:  # noqa: BLE001 -- refused: said where it would print
                self._draws(f"\r\n{why}\r\n".encode(), acked=True)

    def _told(self, message: dict[str, Any], acked: bool) -> None:  # noqa: FBT001
        """Takes a terminal's message on whatever thread, and hands it to the interface's."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._hears(message, acked)
        else:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self._hears, message, acked)

    def _hears(self, message: dict[str, Any], acked: bool) -> None:  # noqa: FBT001
        if self._early is not None:
            self._early.append((message, acked))
            return
        if message.get("term") != self.term or self.ended:
            return
        if message.get("type") == "term_exit":
            status = message.get("status")
            self._ends(
                t("[exited]")
                if status is None
                else t("[exited with status {status}]", status=status)
            )
        elif message.get("type") == "term":
            self._draws(_decoded(message.get("data")), acked=acked)

    def _draws(self, data: bytes, *, acked: bool) -> None:
        """Has the emulator read what was printed, and acknowledges it once enough is."""
        if not data:
            return
        self._stream.feed(data)
        self.refresh()
        if not acked and (drawn := self._credit.took(len(data))) and self.is_attached:
            self.run_worker(
                self._asks("env.term.ack", bytes=drawn),
                group="ack",
                exit_on_error=False,
            )

    def _ends(self, said: str) -> None:
        """Says how the terminal ended where it would have printed, and tells the pane."""
        self.ended = said
        self._stream.feed(f"\r\n{said}\r\n".encode())
        self.refresh()
        self.post_message(self.Ended(self))

    def _answers(self, data: str) -> None:
        self._typed.put_nowait(data.encode())

    def types(self, data: bytes) -> None:
        """Types into the terminal, but for `~.` after a newline, which leaves it.

        Args:
          data: What was typed, as a terminal is sent it.
        """
        sent, leaves = self._escape.typed(data)
        if sent and not self.ended:
            self._typed.put_nowait(sent)
        if leaves:
            self.post_message(self.Left())

    def on_key(self, event: events.Key) -> None:
        """Sends the key to the terminal, and to nothing else."""
        event.stop()
        event.prevent_default()
        key = event.key
        if key in _SENT:
            sent = _SENT[key]
            if key in _CURSOR and _APPLICATION in self._screen.mode:
                sent = sent.replace("[", "O")
        elif event.character:
            sent = event.character
        elif key.startswith("ctrl+") and len(key) == len("ctrl+a"):
            sent = chr(ord(key[-1]) & 0x1F)
        else:
            return
        self.types(sent.encode())

    def on_paste(self, event: events.Paste) -> None:
        """Types what was pasted."""
        event.stop()
        self.types(event.text.encode())

    def on_resize(self, _: events.Resize) -> None:
        """Makes the terminal the size it is drawn at."""
        cols, rows = self._cells()
        if (cols, rows) == (self._screen.columns, self._screen.lines):
            return
        self._screen.resize(rows, cols)
        self.refresh()
        if self.term and not self.ended and self._early is None:
            self.run_worker(
                self._asks("env.term.resize", cols=cols, rows=rows),
                group="size",
                exclusive=True,
                exit_on_error=False,
            )

    def on_focus(self) -> None:
        """Draws the cursor, now that what is typed goes here."""
        self.refresh()

    def on_blur(self) -> None:
        """Stops drawing it."""
        self.refresh()

    def render(self) -> Text:
        """The emulator's screen, the cursor drawn where the keys are here.

        A row is drawn again only where the emulator says it changed, or the cursor came to
        it or left it; the others are as they were drawn last.
        """
        screen = self._screen
        cursor: tuple[int, int] | None = (
            (int(screen.cursor.y), int(screen.cursor.x))
            if self.has_focus and not screen.cursor.hidden and not self.ended
            else None
        )
        size = (int(screen.columns), int(screen.lines))
        if size != self._sized:
            self._sized, self._rows = size, {}
        stale = {int(one) for one in screen.dirty}
        screen.dirty.clear()
        for one in (cursor, self._cursor):
            if one is not None:
                stale.add(one[0])
        self._cursor = cursor
        for y in stale:
            self._rows.pop(y, None)
        drawn = Text(no_wrap=True, end="")
        for y in range(size[1]):
            row = self._rows.get(y)
            if row is None:
                row = self._rows[y] = self._row(y, cursor)
            drawn.append_text(row)
            if y < size[1] - 1:
                drawn.append("\n")
        return drawn

    def _row(self, y: int, cursor: tuple[int, int] | None) -> Text:
        """One row of the emulator's screen, a run of cells of one style at a time."""
        cells = self._screen.buffer[y]
        row = Text(no_wrap=True, end="")
        run: list[str] = []
        held: Style | None = None
        for x in range(self._screen.columns):
            char = cells[x]
            style = _cell(
                char.fg,
                char.bg,
                bold=bool(char.bold),
                italics=bool(char.italics),
                underscore=bool(char.underscore),
                reverse=bool(char.reverse) != ((y, x) == cursor),
            )
            if style is not held:
                if run and held is not None:
                    row.append("".join(run), held)
                run, held = [], style
            # The second cell of a wide character holds nothing, and takes no column.
            run.append(str(char.data))
        if run and held is not None:
            row.append("".join(run), held)
        return row


@dataclass
class _Tab:
    """One terminal of the pane: which it is, what it is called, and what draws it."""

    term: str
    title: str
    tty: Tty | None = None


class _Tabs(Static, can_focus=True):
    """The row of terminals, which has the keys while no terminal does."""

    DEFAULT_CSS = """
    _Tabs { height: auto; padding: 0 1; color: $text-muted; }
    """


class TerminalPane(Pane):
    """An environment's terminals beside the log, as tabs: one drawn, and typed into."""

    PAGE: ClassVar = "shell"
    NONE: ClassVar = "No terminal in this environment"

    DEFAULT_CSS = """
    TerminalPane > #pane-ttys { height: 1fr; }
    """
    BINDINGS: ClassVar = [
        Binding("enter", "into", "Type in", show=False),
        Binding("left", "step(-1)", "Previous", show=False),
        Binding("right", "step(1)", "Next", show=False),
        Binding("n", "new", "New terminal", show=False),
        Binding("x", "close", "Close terminal", show=False),
    ]

    def __init__(self, reach: Reach, host: App[Any]) -> None:
        """Makes the pane.

        Args:
          reach: The host.
          host: The interface.
        """
        super().__init__(reach, host)
        self._tabs: list[_Tab] = []
        self._at = 0

    @property
    def tty(self) -> Tty | None:
        """What draws the terminal shown, or None where there is none."""
        return self._tabs[self._at].tty if self._at < len(self._tabs) else None

    def body(self) -> ComposeResult:
        """The row of terminals, and under it the one shown."""
        yield _Tabs(id="pane-tabs")
        yield Vertical(id="pane-ttys")

    def keys(self) -> list[tuple[str, str]]:
        """`~.` while a terminal has the keys, which takes every other; else the row's."""
        tty = self.tty
        if tty is not None and tty.has_focus:
            return [("~.", "Leave terminal")]
        return [
            ("enter", "Type in"),
            ("left", "Previous"),
            ("right", "Next"),
            ("n", "New terminal"),
            ("x", "Close terminal"),
            *super().keys(),
        ]

    def nothing(self) -> str:
        """That no terminal is open, where none is."""
        return "" if self._tabs else t("No terminal is open here.")

    def aim(self) -> Widget:
        """The terminal shown, while it runs; else the row of terminals."""
        tty = self.tty
        return (
            tty if tty is not None and not tty.ended else self.query_one("#pane-tabs")
        )

    def opened(self) -> None:
        """Lists the terminals of the environment now shown, and opens one where none runs."""
        for tab in self._tabs:
            if tab.tty is not None:
                tab.tty.remove()
        self._tabs, self._at = [], 0
        self._draws_tabs()
        if self._desk is not None:
            self.run_worker(self._reads(first=True), group="list", exclusive=True)

    def freshens(self) -> None:
        """Reads which terminals run again: one may have been opened or ended elsewhere."""
        self.run_worker(self._reads(), group="list", exclusive=True)

    async def _reads(self, *, first: bool = False) -> None:
        """Reads which terminals run in the environment, and what each is called."""
        desk = self._desk
        if desk is None:
            return
        try:
            listed = await desk.asks("env.term.list")
        except Exception as why:  # noqa: BLE001 -- said over the keys
            self.fails(why)
            return
        if self._gone(desk):
            return
        alive = {
            str(one.get("term")): str(one.get("title") or one.get("term"))
            for one in listed.get("terms") or ()
            if one.get("alive", True) and one.get("env", desk.id) == desk.id
        }
        shown = self._tabs[self._at] if self._at < len(self._tabs) else None
        # One ended elsewhere that was never drawn here has nothing to show: its tab goes.
        self._tabs = [
            tab
            for tab in self._tabs
            if tab.tty is not None or not tab.term or tab.term in alive
        ]
        for tab in self._tabs:
            tab.title = alive.pop(tab.term, tab.title)
        self._tabs += [_Tab(term, title) for term, title in alive.items()]
        self._at = self._tabs.index(shown) if shown in self._tabs else 0
        if first:
            within = self.has_focus_within
            if self._tabs:
                await self._shows(0)
            else:
                await self._adds()
            if within:
                self.focus()
        self._draws_tabs()
        self.draws()

    async def _adds(self) -> None:
        """Opens a new terminal in a tab of its own, and shows it."""
        self._tabs.append(_Tab("", t("Terminal")))
        await self._shows(len(self._tabs) - 1)

    async def _shows(self, at: int) -> None:
        """Shows one terminal, opening or coming back to it the first time it is shown."""
        desk = self._desk
        if desk is None or not self._tabs:
            return
        self._at = at % len(self._tabs)
        tab = self._tabs[self._at]
        for other in self._tabs:
            if other.tty is not None:
                other.tty.display = other is tab
        if tab.tty is None:
            tab.tty = Tty(desk, tab.term)
            await self.query_one("#pane-ttys", Vertical).mount(tab.tty)
        self._draws_tabs()
        self.draws()

    def _draws_tabs(self) -> None:
        row = self.query_one("#pane-tabs", _Tabs)
        held = row.has_focus
        parts: list[str] = []
        for at, tab in enumerate(self._tabs):
            ended = f" {t('[exited]')}" if tab.tty is not None and tab.tty.ended else ""
            said = escape(f"{at + 1} {tab.title}{ended}")
            if at == self._at:
                said = f"[b {'reverse ' if held else ''}$primary] {said} [/]"
            else:
                said = f" {said} "
            parts.append(said)
        row.update(f"[$hmz-line-strong]{humanfia.BAR}[/]".join(parts) or t("Terminals"))

    def on_descendant_focus(self, _: events.DescendantFocus) -> None:
        """Draws the row as having the keys or not, and says the keys."""
        self._draws_tabs()
        self.draws()

    def on_descendant_blur(self, _: events.DescendantBlur) -> None:
        """Draws the row again once the keys have settled somewhere."""
        self.call_after_refresh(self._draws_tabs)
        self.call_after_refresh(self.draws)

    @on(Tty.Left)
    def _left(self, event: Tty.Left) -> None:
        event.stop()
        self.query_one("#pane-tabs").focus()

    @on(Tty.Opened)
    def _named(self, event: Tty.Opened) -> None:
        event.stop()
        for tab in self._tabs:
            if tab.tty is event.tty:
                tab.term = event.tty.term
        self.run_worker(self._reads(), group="list", exclusive=True)

    @on(Tty.Ended)
    def _ended(self, event: Tty.Ended) -> None:
        event.stop()
        if event.tty.has_focus:
            self.query_one("#pane-tabs").focus()
        self._draws_tabs()
        self.draws()

    def action_into(self) -> None:
        """Gives the keys to the terminal shown."""
        tty = self.tty
        if tty is not None and not tty.ended:
            tty.focus()

    def action_step(self, by: int) -> None:
        """Shows the terminal before or after the one shown."""
        if len(self._tabs) > 1:
            self.run_worker(self._shows(self._at + by), group="show", exclusive=True)

    def action_new(self) -> None:
        """Opens another terminal, and gives it the keys."""
        self.run_worker(self._news(), group="show", exclusive=True)

    async def _news(self) -> None:
        if self._desk is None:
            return
        await self._adds()
        self.action_into()

    def action_close(self) -> None:
        """Closes the terminal shown, once a box has asked: what runs in it is ended."""
        if self._at < len(self._tabs):
            self.run_worker(self._closes(self._tabs[self._at]), group="do")

    async def _closes(self, tab: _Tab) -> None:
        desk = self._desk
        if desk is None:
            return
        running = tab.tty is None or not tab.tty.ended
        if running:
            sure = await self._host.push_screen_wait(
                Sure(
                    t("Close {name}? What runs in it is ended.", name=tab.title),
                    "",
                    t("Close terminal"),
                )
            )
            if sure != "yes":
                return
        if tab.term:
            try:
                await asyncio.to_thread(
                    desk.reach.ask, "env.term.close", {"term": tab.term}
                )
            except Exception as why:  # noqa: BLE001 -- said over the keys
                if running:
                    self.fails(why)
                    return
        if tab not in self._tabs:
            return
        if tab.tty is not None:
            await tab.tty.remove()
        self._tabs.remove(tab)
        self._said = ""
        if self._tabs:
            await self._shows(min(self._at, len(self._tabs) - 1))
        else:
            self._at = 0
        self.query_one("#pane-tabs").focus()
        self._draws_tabs()
        self.draws()
