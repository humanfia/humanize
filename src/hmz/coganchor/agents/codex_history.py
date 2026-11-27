"""Keep paginated Codex history usable across separate app-server homes."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sqlite3
import stat
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Generator

    from hmz.coganchor.homes import Home

__all__ = ["HistoryBusyError", "persist", "rebind", "record_owner"]

log = logging.getLogger(__name__)

_Binding = tuple[str, str, str, Path, Path]
_PID_LIMIT = 2**31
_UPDATE_PATH = "UPDATE threads SET rollout_path = ? WHERE id = ? AND rollout_path = ?"
_RESTORE_PATH = (
    "UPDATE threads SET rollout_path = ? WHERE id = ? AND rollout_path IN (?, ?)"
)


_LOCK_TIMEOUT = 5.0
_HELD = threading.local()


class HistoryBusyError(TimeoutError):
    """The store lock was unavailable before the history deadline."""


def _codex_canonical(path: Path) -> bool:
    try:
        return path.resolve() == path
    except (OSError, RuntimeError):
        return False


@contextlib.contextmanager
def _codex_history_lock(home: Home, keeps: Path) -> Generator[bool, None, None]:
    import fcntl

    if (
        not _codex_canonical(keeps)
        or not keeps.is_dir()
        or not home.writable(str(keeps))
    ):
        yield False
        return

    held: set[Path] | None = getattr(_HELD, "stores", None)
    if held is None:
        held = _HELD.stores = set[Path]()
    if keeps in held:
        yield True
        return

    with contextlib.ExitStack() as cleanup:
        try:
            directory = os.open(keeps, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            cleanup.callback(os.close, directory)
            deadline = time.monotonic() + _LOCK_TIMEOUT
            while True:
                try:
                    fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise HistoryBusyError(
                            "Codex history is busy; retry the request"
                        ) from None
                    time.sleep(min(0.05, remaining))
        except HistoryBusyError:
            raise
        except OSError as error:
            log.warning("Could not lock the Codex session store %s: %s", keeps, error)
            yield False
            return
        held.add(keeps)
        try:
            yield True
        finally:
            held.remove(keeps)


@contextlib.contextmanager
def rebind(
    home: Home, keeps: Path, thread_id: str, *, keep_active: bool = False
) -> Generator[None, None, None]:
    """Rebind local Codex history for one resume or fork request."""
    with _codex_history_lock(home, keeps) as locked:
        if not locked:
            yield
            return
        with contextlib.ExitStack() as cleanup:
            success = False
            for database in sorted(keeps.glob("state_*.sqlite")):
                if (
                    database.is_symlink()
                    or not database.is_file()
                    or not home.writable(str(database))
                ):
                    continue
                try:
                    uri = database.as_uri() + "?mode=rw"
                    db = cleanup.enter_context(
                        contextlib.closing(sqlite3.connect(uri, uri=True, timeout=5))
                    )
                    changes = _codex_history_changes(db, home, keeps, thread_id)
                    if not changes:
                        continue
                    with db:
                        for thread, previous, active, _, _ in changes:
                            result = db.execute(
                                _UPDATE_PATH,
                                (active, thread, previous),
                            )
                            if result.rowcount != 1:
                                raise sqlite3.OperationalError(
                                    "Codex rollout path changed during rebind"
                                )
                except (sqlite3.Error, OSError, ValueError) as error:
                    log.warning(
                        "Could not rebind Codex rollout paths in %s: %s",
                        database,
                        error,
                    )
                    continue

                def restore(
                    db: sqlite3.Connection = db,
                    changes: list[_Binding] = changes,
                    database: Path = database,
                ) -> None:
                    try:
                        with db:
                            for thread, previous, active, root, saved in changes:
                                if success and keep_active and thread == thread_id:
                                    continue
                                if (
                                    root != keeps
                                    and _codex_home_retired(root)
                                    and saved.is_file()
                                ):
                                    # Codex can save its last path while its controller is retiring.
                                    db.execute(
                                        _RESTORE_PATH,
                                        (str(saved), thread, active, previous),
                                    )
                                else:
                                    db.execute(
                                        _UPDATE_PATH,
                                        (previous, thread, active),
                                    )
                    except sqlite3.Error as error:
                        log.warning(
                            "Could not restore Codex rollout paths in %s: %s",
                            database,
                            error,
                        )

                cleanup.callback(restore)
            yield
            success = True


def _codex_rollout(
    home: Home, keeps: Path, thread_id: object, recorded: object
) -> tuple[Path, Path, str | None] | None:
    """Find and validate the stored rollout for an indexed Codex thread."""
    from uuid import UUID

    if not isinstance(thread_id, str) or not isinstance(recorded, str):
        return None
    try:
        if str(UUID(thread_id)) != thread_id:
            return None
    except ValueError:
        return None
    old = Path(recorded)
    root = (
        keeps
        if old.is_relative_to(keeps)
        else next(
            (
                parent.parent
                for parent in old.parents
                if parent.name in {"sessions", "archived_sessions"}
                and parent.parent.name.startswith("hmz-home-")
            ),
            None,
        )
    )
    if (
        root is None
        or not old.name.startswith("rollout-")
        or not old.name.endswith(f"-{thread_id}.jsonl")
    ):
        return None
    relative = old.relative_to(root)
    if not relative.parts or relative.parts[0] not in {"sessions", "archived_sessions"}:
        return None
    saved = keeps / relative
    if (
        not _codex_canonical(saved)
        or not saved.is_file()
        or not home.readable(str(saved))
    ):
        return None
    try:
        with saved.open("rb") as rollout:
            item = json.loads(rollout.readline())
    except (OSError, ValueError) as error:
        log.warning("Could not read Codex rollout metadata in %s: %s", saved, error)
        return None
    if not isinstance(item, dict):
        return None
    entry = cast("dict[str, object]", item)
    raw_meta = entry.get("payload")
    if entry.get("type") != "session_meta" or not isinstance(raw_meta, dict):
        return None
    meta = cast("dict[str, object]", raw_meta)
    if meta.get("id") != thread_id:
        return None
    base = meta.get("history_base")
    parent = (
        cast("dict[str, object]", base).get("thread_id")
        if isinstance(base, dict)
        else None
    )
    return root, saved, parent if isinstance(parent, str) else None


def _codex_history_changes(
    db: sqlite3.Connection, home: Home, keeps: Path, thread_id: str | None
) -> list[_Binding]:
    """Resolve the requested rollout and any history bases in the same store."""
    changes: list[_Binding] = []
    seen: set[str] = set()
    while isinstance(thread_id, str) and thread_id not in seen:
        seen.add(thread_id)
        row = db.execute(
            "SELECT rollout_path FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
        if row is None or not isinstance(previous := row[0], str):
            break
        found = _codex_rollout(home, keeps, thread_id, previous)
        if found is None:
            break
        root, saved, parent = found
        active = home.at / saved.relative_to(keeps)
        if str(active) != previous:
            changes.append((thread_id, previous, str(active), root, saved))
        thread_id = parent
    return changes


_CODEX_OWNER = ".hmz-codex-owner"


def _codex_boot_id() -> str:
    try:
        return (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        )
    except OSError:
        return ""


def record_owner(home: Home, group: int) -> None:
    """Record the isolated process group so a later server can recognize an abandoned home."""
    if os.name != "posix":
        return
    try:
        descriptor = os.open(
            home.at / _CODEX_OWNER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="ascii") as file:
            file.write(f"{group} {_codex_boot_id()}")
    except OSError as error:
        log.warning("Could not record the Codex home owner in %s: %s", home.at, error)


def _codex_home_retired(root: Path) -> bool:
    """A home qualifies once removed or once its recorded process group has exited."""
    if not root.exists():
        return True
    if os.name != "posix" or not _codex_canonical(root):
        return False
    try:
        descriptor = os.open(
            root / _CODEX_OWNER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        )
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                return False
            owner = os.read(descriptor, 96)
        finally:
            os.close(descriptor)
        pid, _, boot = owner.strip().partition(b" ")
        if not pid.isdigit():
            return False
        group = int(pid)
        if not 1 < group < _PID_LIMIT:
            return False
        current_boot = _codex_boot_id().encode("ascii")
        if boot and current_boot and boot != current_boot:
            return True
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
    except OSError:
        pass
    return False


def persist(home: Home, keeps: Path, *, retiring: bool = False) -> int:
    """Put expired or retiring app-server paths back under the durable store."""
    repaired = 0
    try:
        with _codex_history_lock(home, keeps) as locked:
            if not locked:
                return 0
            for database in sorted(keeps.glob("state_*.sqlite")):
                if (
                    database.is_symlink()
                    or not database.is_file()
                    or not home.writable(str(database))
                ):
                    continue
                try:
                    uri = database.as_uri() + "?mode=rw"
                    with contextlib.closing(
                        sqlite3.connect(uri, uri=True, timeout=5)
                    ) as db:
                        if retiring:
                            prefix = str(home.at) + "/"
                            rows = db.execute(
                                "SELECT id, rollout_path FROM threads "
                                "WHERE substr(rollout_path, 1, ?) = ?",
                                (len(prefix), prefix),
                            ).fetchall()
                        else:
                            rows = db.execute(
                                "SELECT id, rollout_path FROM threads WHERE rollout_path LIKE ?",
                                ("%/hmz-home-%/rollout-%.jsonl",),
                            ).fetchall()
                        changed = 0
                        with db:
                            for thread, old in rows:
                                found = _codex_rollout(home, keeps, thread, old)
                                if found is None:
                                    continue
                                root, saved, _ = found
                                if retiring and root != home.at:
                                    continue
                                if not retiring and (
                                    root == keeps or not _codex_home_retired(root)
                                ):
                                    continue
                                changed += db.execute(
                                    _UPDATE_PATH,
                                    (str(saved), thread, old),
                                ).rowcount
                        repaired += changed
                except (sqlite3.Error, OSError, ValueError) as error:
                    log.warning(
                        "Could not persist Codex rollout paths in %s: %s",
                        database,
                        error,
                    )
    except HistoryBusyError as error:
        log.warning("Could not persist Codex history in %s: %s", keeps, error)
    return repaired
