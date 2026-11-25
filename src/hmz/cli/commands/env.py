"""`hmz env`: the environments of a host -- their files, their git and their terminals.

Everything the page's environment panels do, a command apiece: browsing, reading, writing
against what was read, searching; staging, committing, the log, the snapshots and rewinding;
and a terminal in the environment, handed this one until it ends or is left.
"""

from __future__ import annotations

import contextlib
import datetime
import difflib
import os
import signal
import sys
import threading
from typing import TYPE_CHECKING, Any, Final

from hmz.cli.tree import (
    WORKSPACE,
    YES,
    Arg,
    Command,
    Example,
    Exit,
    Field,
    Unread,
    sure,
    table,
    workspace,
)
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence

    from hmz.cli.tree import Call
    from hmz.sdk.families.envs import (
        Attached,
        Change,
        Entry,
        Env,
        Environment,
        Status,
        Terminal,
    )

__all__ = ["COMMANDS"]

#: The command of `hmz env exec` ran, and did not end with status 0.
FAILED: Final = 5

#: What leaves a terminal running, typed after a newline, as ssh has it.
_LEAVE: Final = b"~."

_THOUSAND: Final = 1000

#: How long a host that lists no environment is given to list one: an epic just started has
#: opened none yet.
_GRACE: Final = 2.0

# -- What a line names ---------------------------------------------------------------------------

_AT = (
    WORKSPACE,
    Arg(
        ("--slot",),
        "which host of the folder to ask: `chat:<id>` for a chat or `exec:<id>` "
        "for an `hmz exec` epic; when not given, the folder's own host, where "
        "its epics run",
        metavar="SLOT",
    ),
    Arg(
        ("--chat",),
        "a chat's id as `hmz chat list` prints it; asks that chat's host "
        "instead of `--workspace` and `--slot`",
        metavar="ID",
    ),
)
_ENV = (
    *_AT,
    Arg(
        ("--env",),
        "which environment of the host to work in, by id, chain or role as `hmz "
        "env list` prints them; when not given, the first open environment",
        metavar="ENV",
    ),
)
_ALL = Arg(("-A", "--all"), "act on every changed path instead of naming paths")


def _calls(*methods: str) -> tuple[str, ...]:
    """The methods a command that attaches to its host calls, its own between them."""
    return ("chat.get", "hosts.status", "epic.attach", *methods, "epic.detach")


@contextlib.contextmanager
def _host(call: Call) -> Generator[Attached]:
    """The host a line names, attached to for as long as the block runs."""
    envs = call.client.envs
    if call.chat:
        host = envs.attached(chat=call.chat)
    else:
        host = envs.attached(workspace(call), slot=call.slot)
    with host:
        yield host


@contextlib.contextmanager
def _env(call: Call) -> Generator[Environment]:
    """The environment a line names: `--env`, or the first that is open."""
    from hmz.sdk import Refused

    with _host(call) as host:
        if not host.envs(_GRACE):
            raise Refused(t("No environment is open here yet."), code=404)
        yield host.env(call.env)


def _notes(call: Call, text: str) -> None:
    """Says something beside the answer, where a person reads it and a program does not."""
    if not call.json:
        print(text, file=sys.stderr)


def _when(mtime: float) -> str:
    return f"{datetime.datetime.fromtimestamp(mtime).astimezone():%Y-%m-%d %H:%M}"


def _size(count: int) -> str:
    size = float(count)
    for unit in ("B", "kB", "MB", "GB"):
        if size < _THOUSAND or unit == "GB":
            return f"{count} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= _THOUSAND
    return f"{count} B"


# -- Environments --------------------------------------------------------------------------------


def _described(env: Env) -> dict[str, Any]:
    return {
        "id": env.id,
        "role": env.role,
        "chain": env.chain,
        "parent": env.parent,
        "run": env.run,
        "backend": env.backend,
        "provider": env.provider,
        "workdir": env.workdir,
        "available": env.available,
        "open": env.open,
        "caps": list(env.caps),
        "declared": list(env.declared),
        "facts": env.facts,
    }


def _state(env: Env) -> str:
    if not env.available:
        return t("unavailable")
    return "" if env.open else t("closed")


def _list(call: Call) -> None:
    with _host(call) as host:
        envs = host.envs(_GRACE)
        call.answers(
            {
                "workspace": host.workspace,
                "slot": host.slot,
                "envs": [_described(one) for one in envs],
            },
            table(
                [
                    [
                        one.id,
                        one.chain,
                        one.backend,
                        one.workdir,
                        ",".join(one.caps),
                        _state(one),
                    ]
                    for one in envs
                ]
            ),
        )
        if not envs:
            _notes(call, t("No environment is open here yet."))


# -- Files ---------------------------------------------------------------------------------------

_KINDS: Final = {"dir": "d", "file": "-", "link": "l"}


def _entry(entry: Entry) -> dict[str, Any]:
    said: dict[str, Any] = {
        "name": entry.name,
        "kind": entry.kind,
        "size": entry.size,
        "mtime": entry.mtime,
        "target": entry.target,
    }
    if entry.path is not None:
        said = {"path": entry.path, **said}
    return said


def _row(entry: Entry, name: str) -> list[str]:
    if entry.kind == "dir":
        name += "/"
    elif entry.target:
        name += f" -> {entry.target}"
    return [
        _KINDS.get(entry.kind, "?"),
        str(entry.size),
        _when(entry.mtime),
        name,
    ]


def _ls(call: Call) -> None:
    with _env(call) as env:
        entries = env.files.list(call.given.path)
    call.answers(
        {"path": call.given.path, "entries": [_entry(one) for one in entries]},
        table([_row(one, one.name) for one in entries]),
    )


def _stat(call: Call) -> None:
    with _env(call) as env:
        entry = env.files.stat(call.given.path)
    call.answers(_entry(entry), table([_row(entry, entry.path or entry.name)]))


def _cat(call: Call) -> None:
    with _env(call) as env:
        read = env.files.read(call.given.path, offset=call.offset, length=call.length)
    if call.json:
        call.answers(
            {
                "path": call.given.path,
                "text": read.data.decode(errors="replace"),
                "size": read.size,
                "mtime": read.mtime,
                "etag": read.etag,
                "eof": read.eof,
            }
        )
        return
    sys.stdout.flush()
    sys.stdout.buffer.write(read.data)
    sys.stdout.buffer.flush()


def _find(call: Call) -> None:
    with _env(call) as env:
        found = env.files.find(limit=call.limit)
    wanted = (call.name or "").lower()
    paths = [one for one in found.paths if wanted in one.lower()]
    call.answers({"paths": paths, "truncated": found.truncated}, paths)
    if found.truncated:
        _notes(
            call, t("There are more results than shown; raise `--limit` to see them.")
        )
    elif not paths:
        _notes(call, t("No matching files."))


def _search(call: Call) -> None:
    with _env(call) as env:
        found = env.files.search(
            call.query,
            regex=call.regex or None,
            case=call.case or None,
            glob=call.glob,
            limit=call.limit,
        )
    call.answers(
        {
            "matches": [
                {
                    "path": one.path,
                    "line": one.line,
                    "column": one.column,
                    "text": one.text,
                }
                for one in found.matches
            ],
            "truncated": found.truncated,
        },
        [f"{one.path}:{one.line}:{one.column}:{one.text}" for one in found.matches],
    )
    if found.truncated:
        _notes(
            call, t("There are more results than shown; raise `--limit` to see them.")
        )
    elif not found.matches:
        _notes(call, t("No results."))


def _write(call: Call) -> None:
    source: str | None = getattr(call.given, "from")
    if source is None:
        data = sys.stdin.buffer.read()
    else:
        with open(source, "rb") as held:  # noqa: PTH123 -- a path as it was typed
            data = held.read()
    with _env(call) as env:
        wrote = env.files.write(call.given.path, data, if_match=call.if_match)
    call.answers(
        {
            "path": call.given.path,
            "etag": wrote.etag,
            "size": wrote.size,
            "mtime": wrote.mtime,
        },
        [t("Saved.")],
    )


def _mkdir(call: Call) -> None:
    with _env(call) as env:
        env.files.mkdir(call.given.path)
    call.answers({"path": call.given.path}, [t("Created")])


def _mv(call: Call) -> None:
    with _env(call) as env:
        env.files.rename(call.given.path, call.to)
    call.answers({"path": call.given.path, "to": call.to}, [t("Renamed")])


def _rm(call: Call) -> None:
    with _env(call) as env:
        sure(call, t("Delete {name}?", name=call.given.path))
        env.files.remove(call.given.path)
    call.answers({"path": call.given.path}, [t("Deleted")])


# -- Commands, as the epic's flow runs them ------------------------------------------------------


def _exec(call: Call) -> int | None:
    from hmz.sdk import Refused

    envs = call.client.envs
    if call.chat:
        at, slot = envs.host(call.chat)
    else:
        at, slot = workspace(call), call.slot
    role: str | None = call.env
    if role is None:
        roles = envs.list(at, slot=slot)
        if not roles:
            raise Refused(t("No environment is open here yet."), code=404)
        role = roles[0].name
    ran = envs.exec(at, role, call.argv, slot=slot, seconds=call.seconds)
    if call.json:
        call.answers({"code": ran.code, "stdout": ran.stdout, "stderr": ran.stderr})
    else:
        sys.stdout.write(ran.stdout)
        sys.stdout.flush()
        sys.stderr.write(ran.stderr)
    return None if ran.code == 0 else FAILED


# -- Git -----------------------------------------------------------------------------------------


def _change(one: Change) -> dict[str, Any]:
    said = {
        "path": one.path,
        "index": one.index,
        "worktree": one.worktree,
        "state": one.state,
    }
    if one.orig is not None:
        said["orig"] = one.orig
    return said


def _branch(status: Status) -> str:
    if status.branch:
        return status.branch
    if status.head:
        return t("{commit} (detached)", commit=status.head[:7])
    return t("No commits yet")


def _upstream(status: Status) -> str:
    if not status.upstream:
        return t("No upstream branch")
    return t(
        "{ahead} ahead of and {behind} behind {upstream}",
        ahead=status.ahead,
        behind=status.behind,
        upstream=status.upstream,
    )


def _status(call: Call) -> None:
    with _env(call) as env:
        status = env.git.status()
    rows = [
        [
            one.index + one.worktree,
            f"{one.orig} -> {one.path}" if one.orig else one.path,
        ]
        for one in status.files
    ]
    call.answers(
        {
            "root": status.root,
            "branch": status.branch,
            "head": status.head,
            "upstream": status.upstream,
            "ahead": status.ahead,
            "behind": status.behind,
            "files": [_change(one) for one in status.files],
        },
        [_branch(status), _upstream(status), *table(rows)],
    )
    if not status.files:
        _notes(call, t("No changes."))


def _staged(one: Change) -> bool:
    return one.index not in ".?"


def _unstaged(one: Change) -> bool:
    return one.worktree != "."


def _unified(path: str, old: bytes | None, new: bytes | None) -> str:
    """One file's change as a unified diff, as `git diff` writes one."""

    def lines(side: bytes | None) -> list[str]:
        # At line feeds alone, as git does: a form feed or a lone carriage return is no end.
        whole = (side or b"").decode(errors="replace").split("\n")
        return [f"{line}\n" for line in whole[:-1]] + [whole[-1]] * bool(whole[-1])

    return "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in difflib.unified_diff(
            lines(old),
            lines(new),
            "/dev/null" if old is None else f"a/{path}",
            "/dev/null" if new is None else f"b/{path}",
        )
    )


def _binary(path: str, old: bytes | None, new: bytes | None) -> str:
    before = t("added") if old is None else t("before {size}", size=_size(len(old)))
    after = t("deleted") if new is None else t("after {size}", size=_size(len(new)))
    return t(
        "{name} is a binary file ({before}, {after}): there is no text to compare.",
        name=path,
        before=before,
        after=after,
    )


def _diff(call: Call) -> None:
    staged = bool(call.staged)
    files: list[dict[str, Any]] = []
    shown: list[str] = []
    with _env(call) as env:
        paths: list[str] = list(call.paths)
        if not paths:
            changed = _staged if staged else _unstaged
            paths = [one.path for one in env.git.status().files if changed(one)]
        for path in paths:
            diff = env.git.diff(path, staged=staged or None)
            text = "" if diff.binary else _unified(path, diff.old, diff.new)
            files.append({"path": path, "binary": diff.binary, "diff": text})
            shown.append(
                _binary(path, diff.old, diff.new) + "\n" if diff.binary else text
            )
    if call.json:
        call.answers({"staged": staged, "files": files})
        return
    sys.stdout.write("".join(shown))
    if not any(shown):
        _notes(call, t("No changes."))


def _log(call: Call) -> None:
    with _env(call) as env:
        commits = env.git.log(limit=call.limit)
    call.answers(
        {
            "commits": [
                {
                    "hash": one.hash,
                    "parents": list(one.parents),
                    "author": one.author,
                    "date": one.date,
                    "subject": one.subject,
                }
                for one in commits
            ]
        },
        table([[one.hash[:7], one.date, one.author, one.subject] for one in commits]),
    )
    if not commits:
        _notes(call, t("No commits yet."))


def _moves(
    which: Callable[[Change], bool],
    does: Callable[[Environment, Sequence[str]], None],
    asks: Callable[[Sequence[str]], str] | None = None,
) -> Callable[[Call], int | None]:
    """A command that stages, unstages or discards: the paths named, or with `--all` every one."""

    def run(call: Call) -> int | None:
        paths: list[str] = list(call.paths)
        if bool(paths) == bool(call.all):
            raise Unread(t("name the paths to act on or pass `--all`, not both"))
        with _env(call) as env:
            if call.all:
                paths = [one.path for one in env.git.status().files if which(one)]
            if paths:
                if asks is not None:
                    sure(call, asks(paths))
                does(env, paths)
        call.answers({"paths": paths}, paths)
        if not paths:
            _notes(call, t("No changes."))
        return None

    return run


def _discards(paths: Sequence[str]) -> str:
    if len(paths) == 1:
        return t("Discard the changes to {name}? This cannot be undone.", name=paths[0])
    return t(
        "Discard the changes to {count} files? This cannot be undone.", count=len(paths)
    )


def _unstages(env: Environment, paths: Sequence[str]) -> None:
    """Unstages paths, and where one was renamed the path it was renamed from."""
    renamed = {one.path: one.orig for one in env.git.status().files if one.orig}
    env.git.unstage([*paths, *(renamed[one] for one in paths if one in renamed)])


_stage = _moves(_unstaged, lambda env, paths: env.git.stage(paths))
_unstage = _moves(_staged, _unstages)
_discard = _moves(_unstaged, lambda env, paths: env.git.discard(paths), _discards)


def _commit(call: Call) -> None:
    with _env(call) as env:
        if call.all:
            paths = [one.path for one in env.git.status().files if _unstaged(one)]
            if paths:
                env.git.stage(paths)
        head = env.git.commit(call.message, amend=call.amend or None)
    call.answers({"head": head}, [head])


def _snapshots(call: Call) -> None:
    with _env(call) as env:
        snapshots = env.git.snapshots()
    call.answers({"snapshots": snapshots}, snapshots)
    if not snapshots:
        _notes(call, t("No snapshots yet."))


def _rewind(call: Call) -> int | None:
    asked = t(
        "Rewind this environment to {ref}? Its working tree is reset to that snapshot: "
        "every change made since, committed or not, is lost.",
        ref=call.ref,
    )
    with _env(call) as env:
        sure(call, asked)
        env.git.rewind(call.ref)
    call.answers(
        {"ref": call.ref}, [t("Rewound the environment to {ref}.", ref=call.ref)]
    )
    return None


# -- Terminals -----------------------------------------------------------------------------------


def _terms(call: Call) -> None:
    with _env(call) as env:
        shells = env.terminals.list()
    call.answers(
        {
            "terms": [
                {
                    "term": one.term,
                    "env": one.env,
                    "title": one.title,
                    "cols": one.cols,
                    "rows": one.rows,
                    "alive": one.alive,
                }
                for one in shells
            ]
        },
        table(
            [
                [
                    one.term,
                    one.title,
                    f"{one.cols}x{one.rows}",
                    "" if one.alive else t("[exited]"),
                ]
                for one in shells
            ]
        ),
    )
    if not shells:
        _notes(call, t("No terminal is open here."))


def _closes(call: Call) -> None:
    with _env(call) as env:
        env.terminals.close(call.term)
    call.answers({"term": call.term}, [t("Closed.")])


def _screen() -> tuple[int, int]:
    """This terminal's size, as columns and rows."""
    try:
        size = os.get_terminal_size(sys.__stdout__.fileno() if sys.__stdout__ else 1)
    except (OSError, ValueError):
        return 80, 24
    return size.columns, size.lines


def _raw(fd: int) -> Callable[[], None]:
    """Puts a terminal in raw mode, answering what puts it back; nothing for one that is not."""
    if not os.isatty(fd):
        return lambda: None
    import termios
    import tty

    # At once, both ways: nothing typed ahead is dropped, and nothing waits on what a
    # terminal that has gone away never reads.
    was = termios.tcgetattr(fd)
    tty.setraw(fd, termios.TCSANOW)
    return lambda: termios.tcsetattr(fd, termios.TCSANOW, was)


class _Typed:
    """What is typed, read for `~.` after a newline: the two keys that leave a terminal running."""

    def __init__(self) -> None:
        self._fresh = True
        self._held = False

    def takes(self, typed: bytes) -> tuple[bytes, bool]:
        """What of `typed` goes to the terminal, and whether it was left."""
        sent = bytearray()
        for byte in typed:
            key = bytes([byte])
            if self._held:
                self._held = False
                if key == _LEAVE[1:]:
                    return bytes(sent), True
                sent += _LEAVE[:1]
                if key == _LEAVE[:1]:
                    continue  # `~~` is one tilde
            if self._fresh and key == _LEAVE[:1]:
                self._held = True
                continue
            self._fresh = key in (b"\r", b"\n")
            sent += key
        return bytes(sent), False


def _bridges(terminal: Terminal, stdin: int, stdout: int) -> bool:
    """Hands this terminal to one in an environment until it ends or is left.

    Returns:
      Whether it was left running.

    Raises:
      Exception: What typing into it was refused with, the terminal put back as it was.
    """
    left = threading.Event()
    failed: list[Exception] = []
    resized = threading.Event()
    over = threading.Event()
    escapes = os.isatty(stdin)

    def types() -> None:
        typed = _Typed()
        try:
            while not over.is_set():
                read = os.read(stdin, 4096)
                if not read:
                    return  # nothing more is typed: what it prints is still read
                sent, leaves = typed.takes(read) if escapes else (read, False)
                if sent:
                    terminal.write(sent)
                if leaves:
                    left.set()
                    terminal.leave()
                    return
        except Exception as why:  # noqa: BLE001 -- refused, or the daemon gone: said below
            if not over.is_set():
                failed.append(why)
                terminal.leave()

    def resizes() -> None:
        while resized.wait() and not over.is_set():
            resized.clear()
            with contextlib.suppress(Exception):
                terminal.resize(*_screen())

    def written(data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(stdout, view) :]

    previous: Any = None
    follows = (
        os.isatty(stdout) and threading.current_thread() is threading.main_thread()
    )
    if follows:

        def winched(_signal: int, _frame: object) -> None:
            resized.set()

        previous = signal.signal(signal.SIGWINCH, winched)
        threading.Thread(target=resizes, daemon=True, name="hmz-env-size").start()
    restore = _raw(stdin)
    threading.Thread(target=types, daemon=True, name="hmz-env-keys").start()
    try:
        written(terminal.replay)
        for printed in terminal:
            written(printed)
    finally:
        over.set()
        resized.set()
        restore()
        if follows:
            signal.signal(signal.SIGWINCH, previous)
    if failed:
        raise failed[0]
    return left.is_set()


def _opens(call: Call) -> None:
    cols, rows = _screen()
    with _env(call) as env:
        terminal = env.terminals.open(
            cols=call.cols or cols, rows=call.rows or rows, term=call.term
        )
        if call.json:
            # Nobody is handed it: it is started, or sized, and left running to come back to.
            terminal.leave()
            call.answers(
                {
                    "term": terminal.id,
                    "shell": None if terminal.shell is None else list(terminal.shell),
                    "replay": terminal.replay.decode(errors="replace"),
                }
            )
            return
        try:
            left = _bridges(terminal, sys.stdin.fileno(), sys.stdout.fileno())
        except KeyboardInterrupt:
            left = True
            terminal.leave()
        if left:
            said = t(
                "Terminal {term} is still running; `hmz env term open --term "
                "{term}` comes back to it.",
                term=terminal.id,
            )
        elif terminal.status is None:
            said = t("[exited]")
        else:
            said = t("[exited with status {status}]", status=terminal.status)
        print(f"\r\n{said}", file=sys.stderr)


# -- The tree ------------------------------------------------------------------------------------

_PATH = Arg(
    ("path",),
    "a path in the environment, relative to its working directory, or absolute",
)
_ENTRY = (
    Field("name", "string", "the entry's file name"),
    Field("kind", "string", "what the entry is: `file`, `dir`, `link` or `other`"),
    Field("size", "integer", "its size in bytes"),
    Field(
        "mtime", "number", "when it was last changed, in seconds since the Unix epoch"
    ),
    Field("target", "string|null", "where a link points, or null if not a link"),
)
_PATHS = Arg(
    ("paths",),
    "the paths to act on, relative to the top of the repository as `hmz env git "
    "status` prints them",
    many=True,
)
_MOVED = (Field("paths", "list", "the paths that were acted on"),)

_FILES = (
    Command(
        "ls",
        "list a directory of an environment",
        args=(
            Arg(
                ("path",),
                "the directory to list, relative to the environment's working "
                "directory, or absolute",
                default=".",
            ),
            *_ENV,
        ),
        examples=(
            Example(
                "hmz env ls", "list the working directory of the first open environment"
            ),
            Example(
                "hmz env ls src --env coder --json",
                "list the directory `src` of the environment `coder` as JSON",
            ),
        ),
        prints=(
            "One line per entry, directories first: its kind (`d` directory, `-` "
            "file, `l` link, `?` other), size in bytes, when it was last changed, "
            "and name."
        ),
        output=(
            Field("path", "string", "the path as given on the command line"),
            Field(
                "entries",
                "list",
                "the entries of the directory, directories first and then by name",
            ),
            *(Field(f"entries[].{one.name}", one.kind, one.says) for one in _ENTRY),
        ),
        methods=_calls("env.list"),
        see=("env stat", "env find", "env cat"),
        run=_ls,
    ),
    Command(
        "stat",
        "show what one path of an environment is",
        args=(_PATH, *_ENV),
        examples=(
            Example(
                "hmz env stat src/app.py --json",
                "print the kind, size and time of one file as JSON",
            ),
        ),
        prints=(
            "One line, as `hmz env ls` prints an entry, with the absolute path in "
            "place of the name."
        ),
        output=(
            Field(
                "path",
                "string",
                "the path as an absolute path on the environment's machine",
            ),
            *_ENTRY,
        ),
        methods=_calls("env.stat"),
        see=("env ls",),
        run=_stat,
    ),
    Command(
        "cat",
        "print a file of an environment",
        says=(
            "Prints the whole file, however long, unless `--offset` or `--length` "
            "asks for a piece of it. With `--json` it also gives the file's `etag`, "
            "which `hmz env write --if-match` takes so a write does not overwrite a "
            "change made since the file was read."
        ),
        args=(
            _PATH,
            Arg(("--offset",), "the byte to start reading at", metavar="N", kind=int),
            Arg(
                ("--length",),
                "how many bytes to read, at most 1048576",
                metavar="N",
                kind=int,
            ),
            *_ENV,
        ),
        examples=(
            Example("hmz env cat README.md", "print a file"),
            Example(
                "hmz env cat README.md --json | jq -r .etag",
                "print the etag of a file, to write it back with `--if-match`",
            ),
            Example(
                "hmz env cat build.log --offset 0 --length 4096",
                "print the first 4096 bytes of a file",
            ),
        ),
        prints="The bytes of the file, exactly as they are.",
        output=(
            Field("path", "string", "the path as given on the command line"),
            Field(
                "text",
                "string",
                "what was read, as UTF-8 text; any byte that is not UTF-8 "
                "becomes U+FFFD",
            ),
            Field("size", "integer", "the size of the whole file in bytes"),
            Field(
                "mtime",
                "number",
                "when the file was last changed, as seconds since the Unix epoch",
            ),
            Field(
                "etag",
                "string",
                "the SHA-256 of the whole file, which `hmz env write --if-match` takes",
            ),
            Field(
                "eof", "boolean", "whether what was read reaches the end of the file"
            ),
        ),
        methods=_calls("env.read"),
        see=("env write", "env ls"),
        run=_cat,
    ),
    Command(
        "find",
        "list the files of an environment, to find one by name",
        says=(
            "Lists the files under the environment's working directory, relative to "
            "it. In a git repository these are the files git tracks or does not "
            "ignore; elsewhere every file outside `.git` and `node_modules`."
        ),
        args=(
            Arg(
                ("name",),
                "print only the paths that contain this text, whatever its "
                "case; when not given, every path",
                default="",
            ),
            Arg(
                ("--limit",),
                "the most files the environment lists; 20000 when not given",
                metavar="N",
                kind=int,
            ),
            *_ENV,
        ),
        examples=(
            Example("hmz env find", "list every file of the environment"),
            Example(
                "hmz env find test_ --json",
                "list the files whose path contains `test_` as JSON",
            ),
        ),
        prints="One path per line, relative to the working directory.",
        output=(
            Field(
                "paths", "list", "the paths found, relative to the working directory"
            ),
            Field(
                "truncated",
                "boolean",
                "whether the environment has more files than `--limit` let it list",
            ),
        ),
        methods=_calls("env.find"),
        see=("env search", "env ls"),
        run=_find,
    ),
    Command(
        "search",
        "search the files of an environment for text",
        args=(
            Arg(
                ("query",),
                "the text to look for, or with `--regex` a regular expression",
            ),
            Arg(
                ("--regex",),
                "read QUERY as a regular expression instead of literal text",
            ),
            Arg(("--case",), "match case; without it `a` also finds `A`"),
            Arg(
                ("--glob",),
                "search only the files whose path matches this glob, such as `*.py`",
                metavar="GLOB",
            ),
            Arg(
                ("--limit",),
                "the most matches to print; 2000 when not given",
                metavar="N",
                kind=int,
            ),
            *_ENV,
        ),
        examples=(
            Example("hmz env search TODO", "find every line that contains `TODO`"),
            Example(
                "hmz env search 'def \\w+_test' --regex --glob '*.py' --json",
                "search the Python files with a regular expression and print "
                "the matches as JSON",
            ),
        ),
        prints="One line per match, as `path:line:column:text`.",
        output=(
            Field("matches", "list", "the matches found"),
            Field(
                "matches[].path",
                "string",
                "the file, relative to the working directory",
            ),
            Field("matches[].line", "integer", "the line number, counting from 1"),
            Field(
                "matches[].column",
                "integer",
                "the column the match starts at, counting from 1",
            ),
            Field("matches[].text", "string", "the line that matched"),
            Field(
                "truncated", "boolean", "whether there were more matches than `--limit`"
            ),
        ),
        methods=_calls("env.search"),
        see=("env find", "env cat"),
        run=_search,
    ),
    Command(
        "write",
        "write a file of an environment from standard input or a local file",
        says=(
            "Makes the file hold what is read from standard input, or from the "
            "local file `--from` names. With `--if-match` it writes only if the "
            "file is still as it was read, and is refused, leaving the file alone, "
            "if it changed since."
        ),
        args=(
            _PATH,
            Arg(
                ("--from",),
                "a file of this machine to read what is written from; when not "
                "given, standard input",
                metavar="FILE",
            ),
            Arg(
                ("--if-match",),
                "write only if the file's etag is still this one, as `hmz env "
                "cat --json` printed it; an empty value, `--if-match ''`, "
                "writes only if there is no file yet",
                metavar="ETAG",
            ),
            *_ENV,
        ),
        examples=(
            Example(
                "echo hello | hmz env write notes/hello.txt",
                "write standard input to a file, making it or replacing what it holds",
            ),
            Example(
                "hmz env write src/app.py --from app.py",
                "write a local file into the environment",
            ),
            Example(
                'hmz env write README.md --from README.md --if-match "$ETAG"',
                "write only if the file has not changed since its etag was read",
            ),
            Example(
                "hmz env write new.txt --from new.txt --if-match ''",
                "write a new file, and refuse if one is already there",
            ),
        ),
        prints="`Saved.`",
        output=(
            Field("path", "string", "the path as given on the command line"),
            Field("etag", "string", "the file's new etag, for the next `--if-match`"),
            Field("size", "integer", "how many bytes the file now holds"),
            Field(
                "mtime",
                "number",
                "when it was written, as seconds since the Unix epoch",
            ),
        ),
        methods=_calls("env.write"),
        see=("env cat", "env mkdir"),
        run=_write,
    ),
    Command(
        "mkdir",
        "make a directory in an environment, with the directories above it",
        args=(_PATH, *_ENV),
        examples=(
            Example(
                "hmz env mkdir docs/guides",
                "make the directory `docs/guides`, and `docs` if it is missing",
            ),
        ),
        prints="Prints `Created`.",
        output=(Field("path", "string", "the path as given on the command line"),),
        methods=_calls("env.mkdir"),
        see=("env write", "env ls"),
        run=_mkdir,
    ),
    Command(
        "mv",
        "move or rename a path of an environment",
        args=(_PATH, Arg(("to",), "the path to move it to"), *_ENV),
        examples=(
            Example("hmz env mv notes.txt docs/notes.md", "move a file and rename it"),
        ),
        prints="Prints `Renamed`.",
        output=(
            Field("path", "string", "the path as given on the command line"),
            Field("to", "string", "the path it was moved to, as it was given"),
        ),
        methods=_calls("env.rename"),
        see=("env rm", "env ls"),
        run=_mv,
    ),
    Command(
        "rm",
        "delete a file or a folder of an environment, and everything in it",
        says=(
            "Deletes the path and everything under it; this cannot be undone. It "
            "asks first; `--yes` skips the question, and is needed where nobody can "
            "be asked: with `--json`, or when standard input is not a terminal."
        ),
        args=(_PATH, YES, *_ENV),
        examples=(
            Example("hmz env rm build", "delete the folder `build` after asking"),
            Example(
                "hmz env rm build --yes --json",
                "delete it without asking, and answer as JSON",
            ),
        ),
        prints="Prints the question on standard error, and then `Deleted`.",
        output=(Field("path", "string", "the path as given on the command line"),),
        methods=_calls("env.remove"),
        see=("env mv", "env git discard"),
        run=_rm,
    ),
)

_GIT = Command(
    "git",
    "see and commit the changes in an environment's git repository",
    says=(
        "These commands work the git repository the environment's working directory "
        "is in, as the Changes panel of the web page does: status, diff and log; "
        "stage, unstage, discard and commit; and the snapshots hmz took, with "
        "rewinding to one. They are refused in an environment that has no git."
    ),
    commands=(
        Command(
            "status",
            "show the branch and the changed files of an environment",
            args=_ENV,
            examples=(
                Example("hmz env git status", "show the branch and what has changed"),
                Example(
                    "hmz env git status --json | jq -r '.files[].path'",
                    "print the path of every changed file",
                ),
            ),
            prints=(
                "Prints the branch, then how far it is ahead of and behind its "
                "upstream, then one line per changed file: two characters for the "
                "index and the working tree, as `git status --short` writes them "
                "with `.` for unchanged, and the path."
            ),
            output=(
                Field("root", "string", "the top directory of the repository"),
                Field(
                    "branch",
                    "string|null",
                    "the branch checked out, or null when none is",
                ),
                Field(
                    "head",
                    "string|null",
                    "the commit checked out, or null before the first commit",
                ),
                Field(
                    "upstream",
                    "string|null",
                    "the branch's upstream, or null when it has none",
                ),
                Field(
                    "ahead",
                    "integer",
                    "how many commits the branch is ahead of its upstream",
                ),
                Field(
                    "behind",
                    "integer",
                    "how many commits the branch is behind its upstream",
                ),
                Field("files", "list", "the changed files"),
                Field(
                    "files[].path",
                    "string",
                    "the file, relative to the top of the repository",
                ),
                Field(
                    "files[].orig",
                    "string",
                    "the path it was renamed or copied from; present only where it was",
                ),
                Field(
                    "files[].index",
                    "string",
                    "one character for its change in the index: `M` modified, "
                    "`A` added, `D` deleted, `R` renamed, `.` unchanged, `?` "
                    "untracked",
                ),
                Field(
                    "files[].worktree",
                    "string",
                    "one character for its change in the working tree, read as "
                    "`index` is",
                ),
                Field(
                    "files[].state",
                    "string",
                    "`conflict` for an unmerged file, `untracked` for an "
                    "untracked one, `changed` otherwise",
                ),
            ),
            methods=_calls("env.git.status"),
            see=("env git diff", "env git stage", "env git commit"),
            run=_status,
        ),
        Command(
            "diff",
            "show the changes to files of an environment as a diff",
            says=(
                "Prints a unified diff of what is not yet staged, the working tree "
                "against the index. With `--staged` it prints what is staged, the "
                "index against the commit checked out. Without paths it covers "
                "every changed file."
            ),
            args=(
                Arg(
                    ("paths",),
                    "the files to show, relative to the top of the repository; "
                    "when none is given, every changed file",
                    many=True,
                ),
                Arg(("--staged",), "show what is staged instead of what is not"),
                *_ENV,
            ),
            examples=(
                Example("hmz env git diff", "show every change that is not staged"),
                Example(
                    "hmz env git diff src/app.py --staged",
                    "show what is staged of one file",
                ),
            ),
            prints=(
                "Prints a unified diff, file after file; a binary file is named in "
                "one line instead."
            ),
            output=(
                Field(
                    "staged", "boolean", "whether this is the diff of what is staged"
                ),
                Field("files", "list", "one entry per file, in the order asked for"),
                Field(
                    "files[].path",
                    "string",
                    "the file, relative to the top of the repository",
                ),
                Field(
                    "files[].binary",
                    "boolean",
                    "whether git reads the file as binary, in which case there "
                    "is no diff text",
                ),
                Field(
                    "files[].diff",
                    "string",
                    "the unified diff of the file, an empty string where "
                    "nothing changed or the file is binary",
                ),
            ),
            methods=_calls("env.git.status", "env.git.diff"),
            see=("env git status", "env git stage"),
            run=_diff,
        ),
        Command(
            "log",
            "list the latest commits of an environment",
            args=(
                Arg(
                    ("--limit",),
                    "the most commits to list; 50 when not given",
                    metavar="N",
                    kind=int,
                ),
                *_ENV,
            ),
            examples=(
                Example("hmz env git log --limit 10", "list the ten latest commits"),
                Example(
                    "hmz env git log --json | jq -r '.commits[0].hash'",
                    "print the hash of the commit checked out",
                ),
            ),
            prints=(
                "One line per commit, newest first: short hash, date, author and "
                "subject."
            ),
            output=(
                Field(
                    "commits",
                    "list",
                    "the commits, from the one checked out, newest first",
                ),
                Field("commits[].hash", "string", "the commit's full hash"),
                Field("commits[].parents", "list", "the hashes of its parent commits"),
                Field("commits[].author", "string", "who wrote it"),
                Field("commits[].date", "string", "when it was written, ISO 8601"),
                Field("commits[].subject", "string", "the first line of its message"),
            ),
            methods=_calls("env.git.log"),
            see=("env git status", "env git snapshots"),
            run=_log,
        ),
        Command(
            "stage",
            "stage changes for the next commit",
            args=(_PATHS, _ALL, *_ENV),
            examples=(
                Example(
                    "hmz env git stage src/app.py README.md",
                    "stage the changes to two files",
                ),
                Example(
                    "hmz env git stage --all",
                    "stage every change, untracked files included",
                ),
            ),
            prints="The paths acted on, one per line.",
            output=_MOVED,
            methods=_calls("env.git.status", "env.git.stage"),
            see=("env git unstage", "env git commit"),
            run=_stage,
        ),
        Command(
            "unstage",
            "take staged changes out of the next commit, keeping them in the files",
            args=(_PATHS, _ALL, *_ENV),
            examples=(
                Example(
                    "hmz env git unstage README.md", "unstage the changes to one file"
                ),
                Example(
                    "hmz env git unstage --all", "unstage everything that is staged"
                ),
            ),
            prints="The paths acted on, one per line.",
            output=_MOVED,
            methods=_calls("env.git.status", "env.git.unstage"),
            see=("env git stage", "env git status"),
            run=_unstage,
        ),
        Command(
            "discard",
            "throw away unstaged changes and delete untracked files",
            says=(
                "Puts each file back as the index has it and deletes the untracked "
                "files named; this cannot be undone. It asks first; `--yes` skips "
                "the question, and is needed where nobody can be asked: with "
                "`--json`, or when standard input is not a terminal."
            ),
            args=(_PATHS, _ALL, YES, *_ENV),
            examples=(
                Example(
                    "hmz env git discard src/app.py",
                    "discard the changes to one file after asking",
                ),
                Example(
                    "hmz env git discard --all --yes",
                    "discard every change that is not staged, without asking",
                ),
            ),
            prints="The paths acted on, one per line.",
            output=_MOVED,
            methods=_calls("env.git.status", "env.git.discard"),
            see=("env git status", "env git rewind"),
            run=_discard,
        ),
        Command(
            "commit",
            "commit what is staged",
            args=(
                Arg(
                    ("-m", "--message"),
                    "the commit message",
                    metavar="TEXT",
                    required=True,
                ),
                Arg(
                    ("--amend",),
                    "amend the commit checked out instead of adding a new one",
                ),
                Arg(
                    ("-a", "--all"),
                    "stage every change first, untracked files included, then commit",
                ),
                *_ENV,
            ),
            examples=(
                Example(
                    "hmz env git commit -m 'fix: handle empty input'",
                    "commit the staged changes",
                ),
                Example(
                    "hmz env git commit --all -m 'docs: update'",
                    "stage every change and commit it",
                ),
                Example(
                    "hmz env git commit --amend -m 'fix: handle no input'",
                    "replace the last commit with what is staged and a new message",
                ),
            ),
            prints="The hash of the new commit.",
            output=(Field("head", "string", "the hash of the new commit"),),
            methods=_calls("env.git.status", "env.git.stage", "env.git.commit"),
            see=("env git stage", "env git log"),
            run=_commit,
        ),
        Command(
            "snapshots",
            "list the snapshots of an environment",
            says=(
                "A snapshot is the whole working tree as it was at one moment, kept "
                "by hmz as a git ref without touching the branch. The list is "
                "oldest first; `hmz env git rewind` takes one of these refs."
            ),
            args=_ENV,
            examples=(
                Example(
                    "hmz env git snapshots", "list the snapshot refs, oldest first"
                ),
                Example(
                    "hmz env git snapshots --json | jq -r '.snapshots[-1]'",
                    "print the latest snapshot ref",
                ),
            ),
            prints="One snapshot ref per line.",
            output=(
                Field(
                    "snapshots",
                    "list",
                    "the snapshot refs, each a ref `hmz env git rewind` takes",
                ),
            ),
            methods=_calls("env.git.snapshots"),
            see=("env git rewind",),
            run=_snapshots,
        ),
        Command(
            "rewind",
            "rewind an environment to a snapshot",
            says=(
                "Resets the working tree to the snapshot; every change made since, "
                "committed or not, is lost. It is refused while an agent is working "
                "in the environment: stop it first. It asks first; `--yes` skips "
                "the question, and is needed with `--json` or when standard input "
                "is not a terminal."
            ),
            args=(
                Arg(
                    ("ref",),
                    "the snapshot to rewind to, a ref as `hmz env git "
                    "snapshots` prints it",
                ),
                YES,
                *_ENV,
            ),
            examples=(
                Example(
                    "hmz env git rewind refs/hmz/snapshots/3",
                    "rewind to a snapshot after asking",
                ),
                Example(
                    "hmz env git rewind refs/hmz/snapshots/3 --yes --json",
                    "rewind without asking, and answer as JSON",
                ),
            ),
            prints=(
                "Prints the question on standard error, and then that the "
                "environment was rewound."
            ),
            output=(
                Field("ref", "string", "the snapshot the environment was rewound to"),
            ),
            methods=_calls("env.git.rewind"),
            see=("env git snapshots", "env git discard"),
            run=_rewind,
        ),
    ),
)

_TERM = Command(
    "term",
    "open, list and close the terminals of an environment",
    says=(
        "A terminal is a shell that runs in an environment. It keeps running when "
        "nobody is attached to it, on the web page or here, until it exits or is "
        "closed; several people can be attached to one at once."
    ),
    commands=(
        Command(
            "open",
            "open a terminal in an environment and attach this terminal to it",
            says=(
                "Starts a shell in the environment's working directory, or comes "
                "back to a running one with `--term`, and attaches this terminal to "
                "it until the shell exits. Typing `~.` at the start of a line "
                "detaches and leaves it running. When standard input is not a "
                "terminal, it is typed into the shell and its output is printed "
                "until the shell exits. With `--json` it does not attach: it starts "
                "the terminal, prints its id and leaves it running."
            ),
            args=(
                Arg(
                    ("--term",),
                    "a running terminal to come back to, by its id as `hmz env "
                    "term list` prints it; when not given, a new terminal is "
                    "started",
                    metavar="ID",
                ),
                Arg(
                    ("--cols",),
                    "how many columns wide the terminal is; when not given, the "
                    "width of this terminal",
                    metavar="N",
                    kind=int,
                ),
                Arg(
                    ("--rows",),
                    "how many rows high the terminal is; when not given, the "
                    "height of this terminal",
                    metavar="N",
                    kind=int,
                ),
                *_ENV,
            ),
            examples=(
                Example(
                    "hmz env term open", "open a shell in the first open environment"
                ),
                Example(
                    "hmz env term open --term t3",
                    "come back to a terminal that was left running",
                ),
                Example(
                    "printf 'make test\\nexit\\n' | hmz env term open",
                    "type two lines into a new shell and print its output until "
                    "it exits",
                ),
                Example(
                    "hmz env term open --json",
                    "start a terminal without attaching, and print its id",
                ),
            ),
            prints=(
                "Prints what the terminal prints, as it prints it, and when it ends "
                "a line on standard error saying how."
            ),
            output=(
                Field(
                    "term",
                    "string",
                    "the terminal's id, which `--term` and `hmz env term close` take",
                ),
                Field(
                    "shell",
                    "list|null",
                    "the command the terminal runs, as a list of words, or null "
                    "for the environment's login shell",
                ),
                Field(
                    "replay",
                    "string",
                    "what a terminal come back to with `--term` had already "
                    "printed, as text; an empty string for a new one",
                ),
            ),
            methods=_calls(
                "env.term.open", "env.term.input", "env.term.resize", "env.term.ack"
            ),
            see=("env term list", "env term close", "env exec"),
            run=_opens,
        ),
        Command(
            "list",
            "list the terminals of an environment",
            args=_ENV,
            examples=(
                Example(
                    "hmz env term list",
                    "list the terminals of the first open environment",
                ),
                Example(
                    "hmz env term list --json | jq -r '.terms[] | "
                    "select(.alive) | .term'",
                    "print the ids of the terminals still running",
                ),
            ),
            prints=(
                "Prints one line per terminal: id, title, size as columns x rows, "
                "and `[exited]` once it has ended."
            ),
            output=(
                Field(
                    "terms",
                    "list",
                    "the terminals that are running, or that somebody still has open",
                ),
                Field("terms[].term", "string", "the terminal's id"),
                Field("terms[].env", "string", "the id of the environment it runs in"),
                Field("terms[].title", "string", "its name, as the page shows it"),
                Field("terms[].cols", "integer", "how many columns wide it is"),
                Field("terms[].rows", "integer", "how many rows high it is"),
                Field("terms[].alive", "boolean", "whether it is still running"),
            ),
            methods=_calls("env.term.list"),
            see=("env term open", "env term close"),
            run=_terms,
        ),
        Command(
            "close",
            "close a terminal, which ends the shell running in it",
            args=(
                Arg(("term",), "the terminal's id, as `hmz env term list` prints it"),
                *_ENV,
            ),
            examples=(
                Example(
                    "hmz env term close t3", "close one terminal and end its shell"
                ),
            ),
            prints="Prints `Closed.`.",
            output=(Field("term", "string", "the id of the terminal that was closed"),),
            methods=_calls("env.term.close"),
            see=("env term list", "env term open"),
            run=_closes,
        ),
    ),
)

COMMANDS = (
    Command(
        "env",
        "work in the environments of a chat or an epic: their files, git and terminals",
        says=(
            "An environment is where the agents of a chat or an epic work, a folder "
            "on this machine, in a container or on another host. These commands do "
            "there what the Environments view of the web page does: browse, read, "
            "write and search files, stage and commit changes, rewind to a "
            "snapshot, run a command and open a terminal. The host is named with "
            "`--workspace` and `--slot`, or with `--chat`; an environment is open "
            "only while its chat or epic is going."
        ),
        commands=(
            Command(
                "list",
                "list the environments of a host",
                says=(
                    "Lists the environments of the chat or epic going on a host, or "
                    "of its last one. An environment derived from another, such as "
                    "a worktree or a clone, is listed after the one it came from. "
                    "The id, chain or role printed here is what `--env` takes in "
                    "the other commands."
                ),
                args=_AT,
                examples=(
                    Example(
                        "hmz env list",
                        "list the environments of the epic going in the current folder",
                    ),
                    Example(
                        "hmz env list -w ~/project --json | jq -r '.envs[].id'",
                        "print the ids of the environments of another folder's epic",
                    ),
                    Example(
                        "hmz env list --chat 20261124-fix-login",
                        "list the environments of a chat",
                    ),
                ),
                prints=(
                    "One line per environment: id, chain, backend, working "
                    "directory, what it serves, and `closed` or `unavailable` where "
                    "it is."
                ),
                output=(
                    Field(
                        "workspace",
                        "string",
                        "the folder of the host that was asked, as the daemon names it",
                    ),
                    Field(
                        "slot",
                        "string",
                        "the slot of the host that was asked, an empty string "
                        "for the folder's own host",
                    ),
                    Field(
                        "envs",
                        "list",
                        "the environments, each root environment in the order "
                        "of its roles and each derived one after the one it "
                        "came from",
                    ),
                    Field(
                        "envs[].id",
                        "string",
                        "the id the host knows the environment by, which `--env` takes",
                    ),
                    Field(
                        "envs[].role",
                        "string",
                        "the environment role it fills in the flow",
                    ),
                    Field(
                        "envs[].chain",
                        "string",
                        "its label: its role followed by each derivation that made it",
                    ),
                    Field(
                        "envs[].parent",
                        "string|null",
                        "the id of the environment it was derived from, or null "
                        "for a root environment",
                    ),
                    Field(
                        "envs[].run", "integer", "the number of the epic it belongs to"
                    ),
                    Field(
                        "envs[].backend",
                        "string",
                        "its kind, such as `local`, `docker` or `ssh`",
                    ),
                    Field("envs[].provider", "string", "the runtime it is on"),
                    Field(
                        "envs[].workdir",
                        "string",
                        "its working directory, on its own machine",
                    ),
                    Field(
                        "envs[].available",
                        "boolean",
                        "whether it can be reached at all",
                    ),
                    Field(
                        "envs[].open",
                        "boolean",
                        "whether it is open; a closed one is listed and refuses "
                        "every command",
                    ),
                    Field(
                        "envs[].caps",
                        "list",
                        "what it serves, of `files`, `shell`, `bash`, `git`, "
                        "`git_worktree`, `rewind`, `scratch` and `temp_clone`; "
                        "a command needs `files`, `git` or `shell`",
                    ),
                    Field(
                        "envs[].declared",
                        "list",
                        "what its role declares in the flow, of the same names "
                        "as `caps`",
                    ),
                    Field(
                        "envs[].facts",
                        "object",
                        "`cpu`, `memory`, `gpu_count` and `gpu_memory` as found "
                        "on its machine, each null where not found",
                    ),
                ),
                methods=_calls(),
                see=("env ls", "env git status", "env term open", "env exec"),
                run=_list,
            ),
            *_FILES,
            Command(
                "exec",
                "run one command in an environment and print what it wrote",
                says=(
                    "Runs the command in the working directory of an environment of "
                    "the epic or chat that is going, as its flow would, waits for "
                    "it to end, and prints its output. Put `--` before the command "
                    "so that its own options are not read as options of hmz. For an "
                    "interactive shell use `hmz env term open`."
                ),
                args=(
                    Arg(
                        ("argv",),
                        "the command and its arguments, after `--`",
                        many=True,
                    ),
                    Arg(
                        ("--seconds",),
                        "how long the command may run before it is stopped, "
                        "from 1 to 3600 seconds; 120 when not given",
                        metavar="N",
                        kind=int,
                    ),
                    *_AT,
                    Arg(
                        ("--env",),
                        "the role of the environment to run in, as `hmz env "
                        "list` prints it; when not given, the first role of the "
                        "flow",
                        metavar="ROLE",
                    ),
                ),
                examples=(
                    Example(
                        "hmz env exec -- git log --oneline -5",
                        "run a command in the environment of the current folder's epic",
                    ),
                    Example(
                        "hmz env exec --env coder --seconds 600 --json -- make test",
                        "run the tests in the environment `coder` for up to ten "
                        "minutes and answer as JSON",
                    ),
                ),
                prints=(
                    "What the command wrote to standard output, on standard output, "
                    "and what it wrote to standard error, on standard error; the "
                    "last 1048576 bytes of each."
                ),
                output=(
                    Field(
                        "code",
                        "integer|null",
                        "the command's exit status, or null if it was stopped "
                        "at its time limit",
                    ),
                    Field(
                        "stdout",
                        "string",
                        "the last 1048576 bytes the command wrote to standard "
                        "output, as text",
                    ),
                    Field(
                        "stderr",
                        "string",
                        "the last 1048576 bytes the command wrote to standard "
                        "error, as text",
                    ),
                ),
                exits=(
                    Exit(
                        FAILED,
                        "the command ran and exited with a status other than 0, "
                        "or was stopped at its time limit",
                    ),
                ),
                methods=("chat.get", "hosts.env.list", "hosts.env.exec"),
                see=("env term open", "env list"),
                run=_exec,
            ),
            _GIT,
            _TERM,
        ),
    ),
)
