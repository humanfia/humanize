"""Epics backed up to git repositories, behind whatever else is going on.

A target is a git repository somebody named in settings, reached as their own git reaches it --
an ssh key, a credential helper -- with nothing signed in here. An epic goes into it as the files
a bundle of it holds, credentials struck out the same way (:func:`hmz.runtime.exporting.unpacked`),
under `<machine>/<workspace>/<epic>/`, so that one repository holds the epics of every machine and
every project and reads file by file. Each backup is one commit, pushed, saying which epic and why.

Nothing here may hold anything else up. A backup is queued and done on a thread of its own, one
queue per target so that two backups to one repository never race in its clone, and an epic
waiting in a queue is not queued twice: the one already waiting will carry whatever has happened
since. How each went is written into the epic itself, as a `backed` line, which is what anybody
reading the epic -- here, in another process, tomorrow -- reads it back from.

The clone a target is committed in is a cache, this machine's alone, under `hmz.machine()`: what
the repository holds is on its remote, and a clone lost is fetched again.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
import threading
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from hmz import machine
from hmz.runtime.epic import BACKED, JOURNAL, note
from hmz.runtime.exporting import MANIFEST, placed, plain, unpacked
from hmz.runtime.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence
    from pathlib import Path

    from hmz.runtime.settings import Target

__all__ = [
    "Keeping",
    "Stored",
    "chosen",
    "configured",
    "listed",
    "pulled",
    "push",
    "wait",
    "where",
]

#: How long one git command is given. A remote that does not answer is a backup that failed,
#: never a thread held for ever.
_PATIENCE = 120.0

#: What a minute is to `interval`, as a test may shorten it.
_MINUTE = 60.0

#: How many directories down a repository keeps an epic: machine, workspace, epic.
_DEEP = 3

#: What a machine's name is flattened to, as a directory of the repository.
_PLAIN = re.compile(r"[^A-Za-z0-9._-]+")

#: The backups waiting, by target, each as the epic and why; the epic each target is backing
#: up now; and the thread working through each target's queue, there while it is not empty.
_HELD = threading.Condition()
_QUEUED: dict[str, list[tuple[Path, str]]] = {}
_WORKING: dict[str, threading.Thread] = {}


def configured() -> tuple[tuple[Target, ...], tuple[str, ...]]:
    """Every backup target in settings, and the names of the defaults among them."""
    return Settings().backups()


def chosen(names: Iterable[str] | None) -> tuple[str, ...]:
    """The targets an epic is to be backed up to, checked against settings.

    Args:
      names: The targets, by name, or None for the defaults.

    Returns:
      Them, each once, in the order given.

    Raises:
      ValueError: For a name no target in settings has.
    """
    targets, defaults = configured()
    if names is None:
        return defaults
    named = tuple(dict.fromkeys(names))
    known = {one.name for one in targets}
    if missing := [one for one in named if one not in known]:
        raise ValueError(f"no backup target is named {', '.join(missing)}")
    return named


def where(epic: Path) -> str:
    """Where in a repository one epic goes: `<machine>/<workspace>/<epic>`."""
    here = _PLAIN.sub("-", socket.gethostname().split(".")[0]) or "machine"
    # Whole, so that `.` is the epic it names rather than a path into nothing.
    epic = epic.resolve()
    return f"{here}/{epic.parent.name}/{epic.name}"


def push(epic: Path, names: Iterable[str], why: str) -> None:
    """Queues one epic to be backed up to each of some targets, and returns at once.

    Args:
      epic: The epic's directory.
      names: The targets, by name.
      why: What it is backed up for -- `session`, `interval`, `end` or `manual` -- which
        its commit says.
    """
    epic = epic.resolve()
    with _HELD:
        for name in names:
            queued = _QUEUED.setdefault(name, [])
            waiting = next(
                (at for at, one in enumerate(queued) if one[0] == epic), None
            )
            if waiting is not None:
                # The backup already waiting carries this one, said as the later reason.
                queued[waiting] = (epic, why)
                continue
            queued.append((epic, why))
            if name not in _WORKING:
                _WORKING[name] = threading.Thread(
                    target=_works,
                    args=(name,),
                    daemon=True,
                    name=f"humanize-backup-{name}",
                )
                _WORKING[name].start()


def wait(seconds: float | None = None) -> bool:
    """Waits for every backup queued in this process to be done, for so long at most.

    Args:
      seconds: How long, or None for as long as it takes -- which every git command it waits
        on is bounded by.

    Returns:
      Whether none is left.
    """
    with _HELD:
        return _HELD.wait_for(lambda: not _WORKING, seconds)


class Stored(NamedTuple):
    """One epic a target holds, as its manifest there says it.

    Attributes:
      key: Where it is in the repository, `<machine>/<workspace>/<epic>`, which is what
        :func:`pulled` is handed.
      machine: The machine it was backed up from, as its directory is named.
      workspace: Where it says it ran, on that machine.
      epic: Its name.
      flow: The flow it ran.
      task: What it was asked to do.
      began: When it began.
      ended: When it ended, or "" for one that had not when it was backed up.
      how: How it ended -- `done`, `failed`, `stopped` -- or "" for one that had not.
      head: The commit its workspace was on, or "" where it said none.
    """

    key: str
    machine: str
    workspace: str
    epic: str
    flow: str
    task: str
    began: str
    ended: str
    how: str
    head: str


def listed(name: str) -> list[Stored]:
    """Every epic one target holds, read off its branch as it is now.

    Fetched first, as a backup fetches, and read file by file out of this machine's clone of
    it: nothing but the fetch goes over the network.

    Args:
      name: The target, by name.

    Returns:
      One per epic, in the order their names sort, which is when each began.

    Raises:
      ValueError: For a name no target in settings has.
      OSError: What git said, where it would not, or took too long.
    """
    target = _target(name)
    found: list[Stored] = []
    with _cloned(target) as at:
        _fetches(at, target.branch)
        for manifest in at.glob(f"*/*/*/{MANIFEST}"):
            epic = manifest.parent
            key = epic.relative_to(at).as_posix()
            if (
                key.startswith(".")
                or not _inside(at, epic)
                or not (epic / JOURNAL).is_file()
            ):
                continue
            try:
                said: object = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(said, dict):
                continue
            run, workspace = (
                _mapping(cast("dict[str, Any]", said).get(one))
                for one in ("run", "workspace")
            )
            ended = str(run.get("ended") or "")
            found.append(
                Stored(
                    key=key,
                    machine=epic.parent.parent.name,
                    workspace=str(workspace.get("at") or ""),
                    epic=epic.name,
                    flow=str(run.get("flow") or ""),
                    task=str(run.get("task") or ""),
                    began=str(run.get("began") or ""),
                    ended=ended,
                    how=str(run.get("how") or "") if ended else "",
                    head=str(workspace.get("head") or ""),
                )
            )
    return sorted(found, key=lambda one: (one.epic, one.key))


def pulled(name: str, key: str) -> Path:
    """Downloads one epic a target holds into this machine's epics, as an import would.

    Args:
      name: The target, by name.
      key: Where the epic is in its repository, `<machine>/<workspace>/<epic>`.

    Returns:
      Where the epic now is: under the workspace it says it ran in.

    Raises:
      ValueError: For a name no target in settings has, a key naming no epic it holds, an
        epic not laid out as one, and one already here -- which an epic this machine backed
        up and still has is.
      OSError: What git said, where it would not, or took too long.
    """
    target = _target(name)
    parts = key.split("/")
    if len(parts) != _DEEP or any(
        not one or one.startswith(".") or "\\" in one for one in parts
    ):
        raise ValueError(f"{key} is not <machine>/<workspace>/<epic>")
    with _cloned(target) as at:
        _fetches(at, target.branch)
        epic = at.joinpath(*parts)
        if not _inside(at, epic) or not (epic / JOURNAL).is_file():
            raise ValueError(f"{name} holds no epic at {key}")
        # Where it came from, with nothing signed into it: the line is read by whoever
        # reads the epic.
        return placed(epic, f"{key} on {name} ({plain(target.url)})")


def _target(name: str) -> Target:
    """One target in settings, by name.

    Raises:
      ValueError: For a name none has.
    """
    found = next((one for one in configured()[0] if one.name == name), None)
    if found is None:
        raise ValueError(f"no backup target is named {name}")
    return found


def _inside(at: Path, epic: Path) -> bool:
    """Whether an epic of a clone is there, rather than wherever a link in it goes."""
    return epic.resolve() == at.resolve().joinpath(epic.relative_to(at))


def _mapping(held: object) -> dict[str, Any]:
    """What a manifest holds under one key, where it is a mapping, and nothing otherwise."""
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}


class Keeping:
    """One epic's backups as it runs: each target's policies, carried out as they come due."""

    def __init__(self, epic: Path, names: Sequence[str]) -> None:
        """Starts backing the epic up every so often to each target whose policy says so.

        Args:
          epic: The epic's directory.
          names: The targets it is backed up to.
        """
        targets = {one.name: one for one in configured()[0]} if names else {}
        self._epic = epic
        # Only those settings still has: one taken out since the run was checked is nowhere.
        self._by = {
            policy: [
                one
                for one in names
                if one in targets and policy in targets[one].policies
            ]
            for policy in ("session", "interval", "end")
        }
        self._over = threading.Event()
        for name in self._by["interval"]:
            threading.Thread(
                target=self._ticks,
                args=(name, targets[name].every * _MINUTE),
                daemon=True,
                name=f"humanize-backup-{name}-tick",
            ).start()

    def closed(self) -> None:
        """A session of the epic closed."""
        push(self._epic, self._by["session"], "session")

    def ended(self) -> None:
        """The epic ended, done, failed or stopped: its ticking stops."""
        self._over.set()
        push(self._epic, self._by["end"], "end")

    def _ticks(self, name: str, seconds: float) -> None:
        while not self._over.wait(seconds):
            push(self._epic, [name], "interval")


def _works(name: str) -> None:
    """Works through one target's queue, and goes once it is empty."""
    while True:
        with _HELD:
            queued = _QUEUED.get(name)
            if not queued:
                _WORKING.pop(name, None)
                _HELD.notify_all()
                return
            epic, why = queued.pop(0)
        _backs_up(name, epic, why)


def _backs_up(name: str, epic: Path, why: str) -> None:
    """Backs one epic up to one target, and writes into the epic how it went."""
    error = f"no backup target is named {name}"
    try:
        target = next((one for one in configured()[0] if one.name == name), None)
        if target is not None:
            _commits(target, epic, why)
            error = ""
    except Exception as failed:  # noqa: BLE001 -- a backup that failed is said, never raised
        error = plain(str(failed) or type(failed).__name__)
    with contextlib.suppress(OSError):
        note(epic, BACKED, to=name, ok=not error, error=error, why=why)


def _commits(target: Target, epic: Path, why: str) -> None:
    """Commits one epic to one target's branch, and pushes it, once more where it raced.

    Raises:
      OSError: What git said, where it would not.
    """
    with _cloned(target) as at:
        if _git(at, "config", "user.email", checked=False).returncode:
            _git(at, "config", "user.name", "hmz")
            _git(at, "config", "user.email", "hmz@localhost")
        into = where(epic)
        for tried in (False, True):
            _fetches(at, target.branch)
            shutil.rmtree(at / into, ignore_errors=True)
            unpacked(epic, at / into)
            _unbacked(at / into / JOURNAL)
            _git(at, "add", "-A", "--", into)
            # Nothing but when the manifest was made is nothing to commit.
            made = f":(exclude){into}/{MANIFEST}"
            if not _git(
                at, "diff", "--cached", "--quiet", "--", into, made, checked=False
            ).returncode:
                return
            _git(at, "commit", "-q", "-m", f"Back up epic {epic.name} ({why})")
            try:
                _git(at, "push", "-q", "origin", f"HEAD:refs/heads/{target.branch}")
            except OSError:
                if tried:
                    raise
            else:
                return


@contextlib.contextmanager
def _cloned(target: Target) -> Generator[Path]:
    """One target's clone, made where it is not, held against every other process using it."""
    at = machine() / "backup" / target.name
    at.mkdir(parents=True, exist_ok=True)
    with _locked(at.with_name(f"{target.name}.lock")):
        # Left by a process that died mid-command: nothing else holds the clone now.
        (at / ".git" / "index.lock").unlink(missing_ok=True)
        _git(at, "init", "-q")
        _git(at, "config", "remote.origin.url", target.url)
        _git(
            at,
            "config",
            "remote.origin.fetch",
            "+refs/heads/*:refs/remotes/origin/*",
        )
        yield at


def _unbacked(journal: Path) -> None:
    """Takes out of an epic's copy the lines saying how it was backed up.

    The copy is what was backed up; how each backup of it went is the epic's own to say, and
    a copy carrying it would differ from the last every time, whatever the epic did.
    """
    with contextlib.suppress(OSError):
        lines = journal.read_text(encoding="utf-8").splitlines(keepends=True)
        mark = f'{{"event": "{BACKED}"'
        journal.write_text(
            "".join(one for one in lines if not one.startswith(mark)), encoding="utf-8"
        )


def _fetches(at: Path, branch: str) -> None:
    """Takes the clone to what the remote's branch holds, or to nothing where it has none."""
    _git(at, "fetch", "-q", "--prune", "origin")
    there = f"refs/remotes/origin/{branch}"
    if not _git(at, "rev-parse", "-q", "--verify", there, checked=False).returncode:
        _git(at, "checkout", "-q", "-f", "-B", branch, there)
    else:
        # An empty repository, or one without the branch: it starts with this commit.
        _git(at, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
        _git(at, "update-ref", "-d", f"refs/heads/{branch}")
        _git(at, "read-tree", "--empty")
    _git(at, "clean", "-q", "-f", "-d", "-x")


def _git(
    at: Path, *said: str, checked: bool = True
) -> subprocess.CompletedProcess[str]:
    """Runs one git command in a clone, never asking anybody anything.

    Raises:
      OSError: If git is not there, took too long, or -- where `checked` -- failed.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if "GIT_SSH_COMMAND" not in env and "GIT_SSH" not in env:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=20"
    try:
        done = subprocess.run(
            ["git", "-C", str(at), *said],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PATIENCE,
            env=env,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as gone:
        raise OSError("git is not installed here") from gone
    except subprocess.TimeoutExpired as slow:
        raise OSError(f"git {said[0]} took longer than {_PATIENCE:.0f}s") from slow
    if checked and done.returncode:
        # Never with what was signed into a URL: what git says is shown to somebody.
        raise OSError(plain(done.stderr.strip()) or f"git {said[0]} failed")
    return done


@contextlib.contextmanager
def _locked(at: Path) -> Generator[None]:
    """Holds one target's clone against every other process backing up to it."""
    with at.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)
