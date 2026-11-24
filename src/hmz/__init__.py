"""Humanize: flows of coding agents, and the runs of them."""

from __future__ import annotations

import contextlib
import contextvars
import fcntl
import functools
import os
import pathlib
import shutil
import stat
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "MOVED",
    "cache",
    "config",
    "data",
    "here",
    "machine",
    "state",
    "working_in",
]

#: What a project's own directory is called, and what it was called before -- as was the
#: home directory's own, which every release before this one kept everything in.
_NAME = ".hmz"
_WAS = ".humanize"

#: What Humanize's directory in each of the user's base directories is called.
_OURS = "humanize"

#: Each kind of directory, by the variable naming its base and the base where that names none.
_BASES = {
    "config": ("XDG_CONFIG_HOME", ".config"),
    "data": ("XDG_DATA_HOME", ".local/share"),
    "state": ("XDG_STATE_HOME", ".local/state"),
    "cache": ("XDG_CACHE_HOME", ".cache"),
}

#: Each entry a release kept in `~/.hmz`, by the kind of directory it is kept in now. What is
#: not here -- `local/`, `server.json`, which nothing reads any more -- stays where it was.
_KINDS = {
    "settings.yaml": "config",
    ".settings.yaml.lock": "config",
    "settings.yaml.migrated": "config",
    "settings.toml": "config",
    ".settings.toml.lock": "config",
    "providers": "data",
    "epics": "data",
    "chats": "data",
    "flowverses": "data",
    "flows": "data",
    "identity": "data",
    "ai": "data",
    "publish": "data",
    "trash": "data",
    "history.jsonl": "state",
    "web-port": "state",
    "envs": "state",
    "easytier": "cache",
}

#: The file in a former home that the move out of it is held on, and that says, once it holds
#: anything, that the move is done: what is left beside it is no release's home, but the
#: directory of the project in the home directory.
MOVED = ".moved"

#: Where a private daemon of this process keeps each kind of directory, while one is up
#: (:mod:`hmz.sdk.private`): told to this process alone, rather than in its environment, which
#: every program it starts -- a coding agent keeping its own in the same bases -- reads too.
_INSTEAD: dict[str, pathlib.Path] = {}

#: The workspace a thread is working in, where it is not the directory being run in.
_WORKING: contextvars.ContextVar[pathlib.Path | None] = contextvars.ContextVar(
    "hmz_working", default=None
)


def config() -> pathlib.Path:
    """Where Humanize keeps what the user set: the settings file.

    `humanize` in `XDG_CONFIG_HOME`, or in `~/.config` where that names no absolute path.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    return _kept("config")


def data() -> pathlib.Path:
    """Where Humanize keeps what it would lose something by losing.

    Epics and chats, accounts, flowverses and the user's own flows, this machine's identity
    and Ai-chan's conversations: `humanize` in `XDG_DATA_HOME`, or in `~/.local/share` where
    that names no absolute path.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    return _kept("data")


def state() -> pathlib.Path:
    """Where Humanize keeps what outlives a run and is no loss to lose.

    The prompt history, the port the web interface last listened on, what environments
    derive from a workdir: `humanize` in `XDG_STATE_HOME`, or in `~/.local/state` where that
    names no absolute path.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    return _kept("state")


def cache() -> pathlib.Path:
    """Where Humanize keeps what it can fetch again: the EasyTier it downloaded.

    `humanize` in `XDG_CACHE_HOME`, or in `~/.cache` where that names no absolute path.

    Returns:
      The directory. It is not made here: it is made by whatever writes into it.
    """
    return _kept("cache")


def here() -> pathlib.Path:
    """Where Humanize keeps what is this project's own: its flows, and the runs exported here.

    `.hmz` in the directory Humanize is being run in. One kept under the name it had before is
    moved to it the first time it is asked for -- unless that is `~/.humanize`, which was no
    project's but what every release kept everything in, and is emptied into the user's
    directories by their rules (:func:`config` and the others) instead.

    Returns:
      The directory, relative to the one being run in -- or under the workspace
      :func:`working_in` names -- kept unresolved, so that a directory since removed is one
      holding nothing rather than a reason to fail. It is not made here.
    """
    working = _WORKING.get()
    at = working / _NAME if working is not None else pathlib.Path(_NAME)
    # Run from the home directory, `~/.hmz` is emptied first: what is left is that project's.
    state()
    # Run in a directory since removed: there is nothing there to move.
    with contextlib.suppress(OSError):
        _project(at.absolute())
    return at


def machine() -> pathlib.Path:
    """Where Humanize keeps what is this machine's alone, made private where it is not yet.

    A home directory is shared by every machine that mounts it, and what is this machine's --
    a process running here, an archive built here -- is nothing another machine can use: one
    reading it would find a pid of somebody else's kernel, and take it for a run of its own
    or a stale one. The temporary directory is the machine's, and one directory in it per
    user, named for the user, is nobody else's. Not `XDG_RUNTIME_DIR`, which is the login
    session's: it goes when the last session does, and what is kept here outlives the
    terminal that started it.

    Returns:
      The directory.

    Raises:
      PermissionError: If what is there under its name is not a directory of this user's
        that nobody else can write. In a temporary directory everybody shares, that is
        somebody else's way of handing this user a file to trust as their own.
    """
    mine = pathlib.Path(tempfile.gettempdir()) / f"humanize-{os.getuid()}"
    with contextlib.suppress(FileExistsError):
        mine.mkdir(mode=0o700)
    found = mine.lstat()
    if (
        not stat.S_ISDIR(found.st_mode)
        or found.st_uid != os.getuid()
        or found.st_mode & 0o022
    ):
        raise PermissionError(
            f"{mine} is not a directory only this user can write; remove it"
        )
    return mine


def _kept(kind: str) -> pathlib.Path:
    """One kind of Humanize's directories, once what a release kept in `~/.hmz` is out of it.

    Args:
      kind: `config`, `data`, `state` or `cache`.

    Returns:
      The directory.
    """
    if (instead := _INSTEAD.get(kind)) is not None:
        return instead
    places = {one: _base(*_BASES[one]) / _OURS for one in _BASES}
    # With `os.path`, which leaves a `~` with no home behind it as it is where `Path` raises:
    # a machine with no home directory has no former home on it, and may still name bases.
    _emptied(pathlib.Path(os.path.expanduser("~")), **places)  # noqa: PTH111
    return places[kind]


def _base(variable: str, otherwise: str) -> pathlib.Path:
    """One of the user's base directories: a relative one is, to the spec, none at all."""
    said = pathlib.Path(os.environ.get(variable, ""))
    return said if said.is_absolute() else pathlib.Path.home() / otherwise


@functools.cache
def _emptied(
    home: pathlib.Path,
    *,
    config: pathlib.Path,
    data: pathlib.Path,
    state: pathlib.Path,
    cache: pathlib.Path,
) -> None:
    """Moves what a release kept in `~/.hmz`, and in `~/.humanize` before it, where it is now.

    Once per process and set of places. Each entry is moved whole, and only while nothing is
    at its new place: where both are there the new one is the one in use, and the old one is
    left as it was rather than merged into it. Nothing raises -- a parent nobody may write, a
    disk that is full: an entry that cannot be moved is left out of use, and tried again by the
    next process, rather than Humanize left unable to start.

    Args:
      home: The user's home directory.
      config: Humanize's config directory.
      data: Its data directory.
      state: Its state directory.
      cache: Its cache directory.
    """
    into = {"config": config, "data": data, "state": state, "cache": cache}
    for old in (home / _NAME, home / _WAS):
        _out_of(old, into)


def _out_of(old: pathlib.Path, into: dict[str, pathlib.Path]) -> None:
    """Moves one former home's entries out, and removes it -- and where it led -- once empty.

    Held on :data:`MOVED` in it, which a second process started at once waits on and then finds
    saying the move is done; and which, left in a former home that still holds what nothing
    reads, says so to every process after -- whatever bases it names, so that one run with
    bases of a scratch directory's takes nothing of the user's into it.

    Args:
      old: `~/.hmz` or `~/.humanize`. A link -- as a release's `hmz home move` left `~/.hmz`
        -- is emptied where it leads.
      into: Each kind of directory, by its kind.
    """
    try:
        held = old.resolve(strict=True)
        marked = (held / MOVED).open("a+", encoding="utf-8")
    except (OSError, RuntimeError):
        return
    with marked, contextlib.suppress(OSError):
        fcntl.flock(marked, fcntl.LOCK_EX)
        marked.seek(0)
        if marked.read():
            return
        # Every one tried, whether or not one before it could be moved.
        moved = [
            _moved_out(held / one.name, into[_KINDS[one.name]])
            for one in list(held.iterdir())
            if one.name in _KINDS
        ]
        if not all(moved):
            return
        marked.write("moved\n")
        marked.flush()
        if {one.name for one in held.iterdir()} == {MOVED}:
            (held / MOVED).unlink()
            held.rmdir()
            if old.is_symlink():
                old.unlink()


def _moved_out(entry: pathlib.Path, into: pathlib.Path) -> bool:
    """Moves one entry of a former home into its directory, where nothing is there by its name.

    Beside its place first and renamed into it, so that what is at its place is whole: a copy
    to another device that stops partway is left beside it, under a name nothing reads.

    Args:
      entry: The entry.
      into: The directory it goes in.

    Returns:
      Whether it is out of the former home, or was left there because it is already in use.
    """
    if os.path.lexists(into / entry.name):
        return True
    beside = into / f".{entry.name}.{os.getpid()}.moving"
    try:
        into.mkdir(parents=True, exist_ok=True)
        shutil.move(entry, beside)
        beside.rename(into / entry.name)
    except (OSError, shutil.Error):
        return False
    _repaired(into / entry.name)
    return True


def _repaired(moved: pathlib.Path) -> None:
    """Tells git where each worktree a move took along now is, as `git worktree repair` does.

    A worktree's repository names it by its path, and one it no longer finds there it takes
    for one removed, to be pruned. Only `envs/` holds worktrees; one git cannot repair is left
    as it is, as anything else the move could not do.

    Args:
      moved: The entry, at its new place.
    """
    if moved.name != "envs":
        return
    import subprocess

    for worktree in moved.glob("*/worktrees/*"):
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["git", "worktree", "repair"],
                cwd=worktree,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=30,
            )


@functools.cache
def _project(at: pathlib.Path) -> None:
    """Moves a project's own directory where what was there before is not `~/.humanize`.

    Args:
      at: The project's directory, whole.
    """
    was = at.with_name(_WAS).resolve()
    # With `os.path`, which leaves a `~` with no home behind it as it is where `Path` raises:
    # a machine with no home directory has no `~/.humanize` for a project to be mistaken for.
    yours = pathlib.Path(os.path.expanduser("~/" + _WAS))  # noqa: PTH111
    if was != yours.resolve():
        _moved(at)


def _moved(at: pathlib.Path) -> None:
    """A project's own directory, with the one it was before moved to it where need be.

    Moved in one rename, and only while nothing is at the new place: where both are there the
    new one is the one in use, and the old one is left as it was rather than merged into it.

    Args:
      at: Where the directory is now, beside where it was.
    """
    # Nothing to move, or nowhere it could go -- a parent nobody may write, another device:
    # either way the old one is left out of use rather than Humanize left unable to start.
    with contextlib.suppress(OSError):
        if not at.exists():
            at.with_name(_WAS).rename(at)


@contextlib.contextmanager
def working_in(workspace: str | os.PathLike[str]) -> Generator[None]:
    """Answers :func:`here` under one workspace rather than the directory being run in.

    For this thread, and whatever it calls, until the block ends: what lets one process -- the
    web interface, serving every workspace of a machine -- find each one's own flows without
    moving the directory everything else in the process is run in.

    Args:
      workspace: The workspace.

    Yields:
      Nothing; inside the block, :func:`here` is `<workspace>/.hmz`.
    """
    token = _WORKING.set(pathlib.Path(workspace))
    try:
        yield
    finally:
        _WORKING.reset(token)
