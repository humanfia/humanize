"""A lazily materialised local mirror of the target's workspace.

The shadow tree is what makes interception cheap.  Instead of forwarding every
``read`` and ``getdents64``, coganchor reproduces the target's *structure*
locally the first time a directory is touched: real directories, real
symlinks, and sparse placeholder files carrying the remote size, mode and
mtime.  From then on ``stat``, ``getdents64``, ``read``, ``write``, ``mmap``
and ``lseek`` all run natively at full speed and still tell the truth.

Only two things cross the network per file:

* **content pull** -- the first time a file is opened for reading, and
* **content push** -- when a locally modified file must become visible to
  the target, which happens before any remote command runs.

A remote command may change anything, so finishing one bumps a *generation*
counter that invalidates every cached directory listing.

Several turns may work in one mirror at once, each a supervisor process of its
own.  What a tree knows about the mirror -- which files hold their content, which
were written and not yet pushed -- is what keeps it from deleting or zeroing what
is there, so the turns share it: see :class:`_Ledger`.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import logging
import os
import shutil
import stat as stat_module
from dataclasses import astuple, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.coganchor import atomic

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from hmz.coganchor.policy import Layout, Router
    from hmz.coganchor.remote import RemoteClient

__all__ = ["ShadowTree", "prepare_shadow_root"]

log = logging.getLogger(__name__)

#: Shadow roots are recorded here rather than marked in place, so the mirror
#: stays byte-for-byte what the target has -- an agent listing the workspace
#: must not see coganchor's own bookkeeping.
REGISTRY_DIR = "~/.cache/humanize/shadows"

#: What points that somewhere else for one process and everything it starts. For a machine
#: that keeps its caches elsewhere, and for a test suite: these records outlive the mirrors
#: they are about, so a suite writing them into somebody's own cache is a suite that leaves
#: thousands of them there and then reads one back as a mirror it never made.
SHADOWS = "HUMANIZE_SHADOWS"

_FETCH_SUFFIX = ".humanize-fetch"

#: Bound on symlink chasing, matching the kernel's own ``ELOOP`` limit.
_MAX_LINK_HOPS = 40


@dataclass(slots=True)
class FileRecord:
    """What coganchor last knew about one file, on both sides."""

    kind: str
    mode: int
    remote_size: int
    remote_mtime_ns: int
    content_present: bool = False
    local_size: int = -1
    local_mtime_ns: int = -1

    def matches_remote(self, entry: dict[str, Any]) -> bool:
        return bool(
            self.kind == entry["kind"]
            and self.remote_size == entry["size"]
            and self.remote_mtime_ns == entry["mtime_ns"]
        )


class _Ledger:
    """What every turn working in one mirror knows about it, kept beside its record.

    Each turn is a supervisor process of its own, and a tree that knows only what its own
    turn did takes the others' work for something to put right. A file another turn has
    written and not pushed yet is one the target lacks, and is swept away; one it has pushed
    or fetched is one this tree has no record of, and is made a placeholder again -- which
    that turn then reads as its content, or pushes as its own edit, zeroes and all.

    So what a tree changes in what it knows is appended to a journal here, and what the others
    changed is read from it, under a lock each holds for as long as it changes the mirror:
    every turn in a mirror is then one tree, as every process of one agent always was. A
    journal nobody else is reading is begun again -- a turn alone in a mirror knows what one
    always has, nothing -- which a lock each turn holds shared for as long as it lives tells.

    Args:
      base: Where the two files are kept, less their suffixes.

    Raises:
      OSError: If they cannot be opened or locked here.
    """

    def __init__(self, base: str) -> None:
        import fcntl

        os.makedirs(os.path.dirname(base), exist_ok=True)
        flags = os.O_CREAT | os.O_CLOEXEC
        self._journal = os.open(
            base + ".journal", flags | os.O_RDWR | os.O_APPEND, 0o600
        )
        try:
            self._live = os.open(base + ".live", flags | os.O_RDONLY, 0o600)
        except OSError:
            os.close(self._journal)
            raise
        self._seen = 0
        self._depth = 0
        self._told: list[bytes] = []
        try:
            fcntl.flock(self._journal, fcntl.LOCK_EX)
            try:
                try:
                    fcntl.flock(self._live, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass  # another turn is here: what it knows is where this one starts
                else:
                    os.ftruncate(self._journal, 0)
                fcntl.flock(self._live, fcntl.LOCK_SH)
            finally:
                fcntl.flock(self._journal, fcntl.LOCK_UN)
        except OSError:
            os.close(self._journal)
            os.close(self._live)
            raise

    @contextlib.contextmanager
    def held(self, replay: Callable[[list[Any]], None]) -> Generator[None]:
        """Holds the mirror for the block, having first caught up with the other turns.

        Args:
          replay: What applies one entry another turn appended.
        """
        import fcntl

        if not self._depth:
            fcntl.flock(self._journal, fcntl.LOCK_EX)
            try:
                self._catch_up(replay)
            except BaseException:
                fcntl.flock(self._journal, fcntl.LOCK_UN)
                raise
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            if not self._depth:
                try:
                    self._write_out()
                finally:
                    fcntl.flock(self._journal, fcntl.LOCK_UN)

    def close(self) -> None:
        """Lets go of the mirror: the turns still in it go on without this one."""
        os.close(self._journal)
        os.close(self._live)

    def tell(self, entry: list[Any]) -> None:
        """Appends one change, for the others to read once the mirror is let go of."""
        self._told.append(json.dumps(entry, separators=(",", ":")).encode())

    def _catch_up(self, replay: Callable[[list[Any]], None]) -> None:
        end = os.fstat(self._journal).st_size
        chunks: list[bytes] = []
        while self._seen < end:
            chunk = os.pread(self._journal, end - self._seen, self._seen)
            if not chunk:
                break
            chunks.append(chunk)
            self._seen += len(chunk)
        for line in b"".join(chunks).splitlines():
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue  # half a line, from a turn killed while writing it
            replay(entry)

    def _write_out(self) -> None:
        if not self._told:
            return
        # Begun on a line of its own, so that half of one a killed turn left is only that.
        blob = memoryview(b"\n" + b"\n".join(self._told) + b"\n")
        self._told.clear()
        try:
            while blob:
                blob = blob[os.write(self._journal, blob) :]
        except OSError as why:
            log.warning(
                "the other turns in this mirror will not hear of a change: %s", why
            )
        self._seen = os.fstat(self._journal).st_size


class ShadowTree:
    """Keeps the local mirror consistent with the target.

    Args:
      client: The target.
      router: Which paths are the target's, and as what.
      mirror: The mirror's root, for a tree to share what it knows with every other turn
        working in it; None for one that keeps it to itself.
    """

    def __init__(
        self, client: RemoteClient, router: Router, mirror: str | None = None
    ) -> None:
        self._client = client
        self._router = router
        self._dirs: dict[str, int] = {}
        self._files: dict[str, FileRecord] = {}
        self._dirty_candidates: set[str] = set()
        self._generation = 0
        self._ledger: _Ledger | None = None
        if mirror is not None:
            try:
                self._ledger = _Ledger(_registry_entry(mirror).removesuffix(".json"))
            except OSError as why:
                log.warning(
                    "%s cannot be shared with other turns working in it, which may then "
                    "lose what this one writes: %s",
                    mirror,
                    why,
                )

    def close(self) -> None:
        """Stops sharing what this tree knows, for the other turns in the mirror to go on alone.

        A tree not closed is let go of when its process ends.
        """
        if self._ledger is not None:
            self._ledger.close()
            self._ledger = None

    # ------------------------------------------------------------------ queries

    def invalidate(self) -> None:
        """Forget every cached listing, because the target may have changed."""
        self._generation += 1

    # ------------------------------------------------------------ materialising

    def ensure_path(self, local_path: str) -> None:
        """Make ``local_path`` resolvable: materialise the directory holding it."""
        parent = os.path.dirname(local_path.rstrip("/")) or "/"
        self.ensure_directory(parent)

    def ensure_directory(self, local_dir: str) -> None:
        """Mirror one remote directory locally, at most once per generation."""
        layout = self._router.layout_for(local_dir)
        if layout is None or self._dirs.get(local_dir) == self._generation:
            return
        with self._shared():
            self.flush()
            virtual = layout.to_virtual(local_dir)
            try:
                listing = self._client.listdir(virtual)
            except OSError as exc:
                if exc.errno in (errno.ENOENT, errno.ENOTDIR, errno.EACCES):
                    self._dirs[local_dir] = self._generation
                    self._drop_local(local_dir)
                    return
                raise
            self._apply_listing(layout, local_dir, listing)
            self._dirs[local_dir] = self._generation

    def ensure_content(self, local_path: str) -> None:
        """Fetch a file's bytes if the local copy is still a placeholder."""
        if not self._router.is_remote_path(local_path):
            return
        with self._shared():
            self.ensure_path(local_path)
            # Opening a symlink reads whatever it points at, so that is the file
            # whose content has to be here.
            path = self._follow_links(local_path)
            layout = self._router.layout_for(path)
            record = self._files.get(path)
            if layout is None or record is None or record.kind != "file":
                return
            # Here already, or written over since: newer than what the target has to give.
            if record.content_present or self._unpushed(path):
                return
            virtual = layout.to_virtual(path)
            scratch = path + _FETCH_SUFFIX
            try:
                with open(scratch, "wb") as sink:
                    meta = self._client.read_file(virtual, sink)
                os.chmod(scratch, stat_module.S_IMODE(record.mode))
                os.replace(scratch, path)
            except OSError:
                _unlink_quietly(scratch)
                raise
            os.utime(path, ns=(meta["mtime_ns"], meta["mtime_ns"]))
            record.remote_size = meta["size"]
            record.remote_mtime_ns = meta["mtime_ns"]
            record.content_present = True
            self._record_local_state(path, record)
            self._keep(path, record)

    def _follow_links(self, local_path: str) -> str:
        """Resolve local symlinks, materialising each directory on the way."""
        path = local_path
        for _ in range(_MAX_LINK_HOPS):
            try:
                target = os.readlink(path)
            except OSError:
                return path
            path = os.path.normpath(os.path.join(os.path.dirname(path), target))
            if not self._router.is_remote_path(path):
                return path
            self.ensure_path(path)
        return path

    def duplicate(self, source: str, target: str) -> None:
        """Record that ``target`` now aliases ``source``, as a hard link does.

        Without this the new name has no record, so a placeholder that was
        never fetched would be read as zeroes through it.
        """
        with self._shared():
            record = self._files.get(source)
            if record is None:
                return
            copy = replace(record)
            self._record_local_state(target, copy)
            self._keep(target, copy)

    def note_write(self, local_path: str) -> None:
        """Remember that the tracee is about to write here, so ``flush`` looks."""
        if not self._router.is_remote_path(local_path):
            return
        with self._shared():
            if local_path not in self._dirty_candidates:
                self._dirty_candidates.add(local_path)
                self._tell("dirty", local_path)

    def forget(self, local_path: str) -> None:
        """Drop state for a path the tracee removed or renamed away."""
        with self._shared():
            self._drop(local_path)
            self._tell("forget", local_path)

    def _drop(self, local_path: str) -> None:
        covers = _subtree_test(local_path)
        self._files = {
            key: value for key, value in self._files.items() if not covers(key)
        }
        self._dirs = {
            key: value for key, value in self._dirs.items() if not covers(key)
        }
        self._dirty_candidates = {
            path for path in self._dirty_candidates if not covers(path)
        }

    def rename(self, source: str, target: str) -> None:
        """Carry cached state across a rename the tracee just performed.

        Without this a renamed placeholder would lose its record, so its
        content would never be fetched and the file would read as zeroes.
        """
        with self._shared():
            self._move(source, target)
            self._tell("rename", source, target)

    def _move(self, source: str, target: str) -> None:
        self._drop(target)
        covers = _subtree_test(source)
        rebase = _subtree_rebase(source, target)
        self._files = {
            rebase(key) if covers(key) else key: v for key, v in self._files.items()
        }
        self._dirs = {
            rebase(key) if covers(key) else key: v for key, v in self._dirs.items()
        }
        self._dirty_candidates = {
            rebase(path) if covers(path) else path for path in self._dirty_candidates
        }

    # -------------------------------------------------------------- write-back

    def flush(self) -> int:
        """Push every locally modified file to the target.

        Called before any remote command runs and before re-reading a
        directory, so the target never observes stale content.  Returns the
        number of files pushed.

        Every turn working in the mirror is flushed for, whichever does it: a file another
        turn wrote is on the target before this one reads a directory holding it.
        """
        with self._shared():
            return self._flush()

    def _flush(self) -> int:
        pushed = 0
        for local_path in sorted(self._dirty_candidates):
            layout = self._router.layout_for(local_path)
            if layout is None:
                continue
            try:
                info = os.lstat(local_path)
            except OSError:
                continue  # removed locally; the unlink was replayed already
            if not stat_module.S_ISREG(info.st_mode):
                continue
            record = self._files.get(local_path)
            if (
                record is not None
                and record.local_size == info.st_size
                and record.local_mtime_ns == info.st_mtime_ns
            ):
                continue
            self._push(layout, local_path, info)
            pushed += 1
        return pushed

    def _push(self, layout: Layout, local_path: str, info: os.stat_result) -> None:
        virtual = layout.to_virtual(local_path)
        with open(local_path, "rb") as source:
            meta = self._client.write_file(virtual, source, info.st_mode)
        # As it was before it was read: a write landing while it was being sent is one the
        # next flush sees, not one taken for what went.
        record = FileRecord(
            kind="file",
            mode=info.st_mode,
            remote_size=meta.get("size", info.st_size),
            remote_mtime_ns=meta.get("mtime_ns", 0),
            content_present=True,
            local_size=info.st_size,
            local_mtime_ns=info.st_mtime_ns,
        )
        self._keep(local_path, record)
        log.debug("pushed %s -> %s (%d bytes)", local_path, virtual, info.st_size)

    # ---------------------------------------------------------------- internals

    def _apply_listing(
        self,
        layout: Layout,  # noqa: ARG002  -- the caller resolved against it already
        local_dir: str,
        listing: dict[str, Any],
    ) -> None:
        os.makedirs(local_dir, exist_ok=True)
        expected: set[str] = set()
        for entry in listing["entries"]:
            name = entry["name"]
            expected.add(name)
            self._apply_entry(os.path.join(local_dir, name), entry)
        self._remove_vanished(local_dir, expected)

    def _apply_entry(self, local_path: str, entry: dict[str, Any]) -> None:
        if self._unpushed(local_path):
            return  # the next flush carries it there, over whatever the target has
        kind = entry["kind"]
        if kind == "dir":
            self._apply_dir(local_path, entry)
        elif kind == "link":
            self._apply_link(local_path, entry)
        else:
            self._apply_file(local_path, entry)

    def _apply_dir(self, local_path: str, entry: dict[str, Any]) -> None:
        if os.path.islink(local_path) or (
            os.path.exists(local_path) and not os.path.isdir(local_path)
        ):
            _remove_any(local_path)
        os.makedirs(local_path, exist_ok=True)
        record = FileRecord(
            kind="dir",
            mode=entry["mode"],
            remote_size=entry["size"],
            remote_mtime_ns=entry["mtime_ns"],
            content_present=True,
        )
        if self._files.get(local_path) != record:
            self._keep(local_path, record)

    def _apply_link(self, local_path: str, entry: dict[str, Any]) -> None:
        target = entry.get("target", "")
        try:
            if os.readlink(local_path) == target:
                return
        except OSError:
            pass
        _remove_any(local_path)
        os.symlink(target, local_path)
        self._keep(
            local_path,
            FileRecord(
                kind="link",
                mode=entry["mode"],
                remote_size=entry["size"],
                remote_mtime_ns=entry["mtime_ns"],
                content_present=True,
            ),
        )

    def _apply_file(self, local_path: str, entry: dict[str, Any]) -> None:
        record = self._files.get(local_path)
        if (
            record is not None
            and record.matches_remote(entry)
            and _is_intact(local_path, record)
        ):
            return
        if os.path.isdir(local_path) and not os.path.islink(local_path):
            _remove_any(local_path)
        fresh = FileRecord(
            kind=entry["kind"],
            mode=entry["mode"],
            remote_size=entry["size"],
            remote_mtime_ns=entry["mtime_ns"],
            content_present=entry["size"] == 0 and entry["kind"] == "file",
        )
        # A sparse placeholder of the right size, mode and mtime makes local
        # stat(), getdents64() and ls() report the target's truth for free.
        with open(local_path, "wb") as handle:
            if entry["size"] and entry["kind"] == "file":
                handle.truncate(entry["size"])
        os.chmod(local_path, stat_module.S_IMODE(entry["mode"]))
        os.utime(local_path, ns=(entry["mtime_ns"], entry["mtime_ns"]))
        self._record_local_state(local_path, fresh)
        self._keep(local_path, fresh)

    def _remove_vanished(self, local_dir: str, expected: set[str]) -> None:
        try:
            present = set(os.listdir(local_dir))
        except OSError:
            return
        for name in present - expected:
            # Scratch files from an interrupted fetch are swept too: nothing
            # else ever removes them, and a fetch can never be in flight here
            # because both run holding the mirror, whichever turn runs them.
            path = os.path.join(local_dir, name)
            if self._unpushed(path):
                continue  # made since the flush before this listing: the next one sends it
            self._note_unforwarded(path)
            _remove_any(path)
            self.forget(path)

    def _note_unforwarded(self, path: str) -> None:
        """Say out loud when what is about to be dropped was never carried across.

        The mirror is authoritative, so anything in it the target has not got is deleted --
        which is right for a file the target removed, and is silent data loss for one this
        layer never noticed being written.  The two are told apart by whether there is a
        record: a file mirrored *from* the target has one, and a file that appeared in the
        mirror without passing a handler has none.  That is exactly the shape of a write
        made through a path the prefix rules did not recognise, and what made the first one
        of those expensive was that it looked like nothing at all -- the agent read the file
        back through its plain name, reported success, and the bytes were swept away here
        without a word.

        It is still swept, because the mirror being authoritative is what the session
        promises; this only refuses to do it quietly.

        Only a regular file of the target's own is worth saying it about.  A directory may
        have been made here on the way to materialising something under it and hold nothing;
        a path the session keeps local is not the target's to have; and the scratch of an
        interrupted fetch is this layer's own litter.

        Args:
          path: The file in the mirror, about to be removed.
        """
        layout = self._router.layout_for(path)
        if (
            path in self._files
            or layout is None
            or path.endswith(_FETCH_SUFFIX)
            or os.path.islink(path)
            or not os.path.isfile(path)
        ):
            log.debug("dropping %s: gone on the target", path)
            return
        log.warning(
            "%s was written here but never reached the target as %s, and is being dropped; "
            "the agent may have been told it succeeded",
            path,
            layout.to_virtual(path),
        )

    def _drop_local(self, local_dir: str) -> None:
        """The directory no longer exists remotely; remove the local mirror."""
        if os.path.isdir(local_dir) and not os.path.islink(local_dir):
            _remove_any(local_dir)
        self.forget(local_dir)

    def _unpushed(self, local_path: str) -> bool:
        """Whether a file here was written since it was last pushed, by any turn in the mirror.

        Such a file is newer than anything the target says of it. A flush is what finds
        them, and each listing is read right after one -- but a turn's write lands when its
        own process gets to it, which is no later than this turn's next look only for a turn
        that is this one.
        """
        if local_path not in self._dirty_candidates:
            return False
        try:
            info = os.lstat(local_path)
        except OSError:
            return False
        if not stat_module.S_ISREG(info.st_mode):
            return False
        record = self._files.get(local_path)
        return record is None or (record.local_size, record.local_mtime_ns) != (
            info.st_size,
            info.st_mtime_ns,
        )

    @contextlib.contextmanager
    def _shared(self) -> Generator[None]:
        """Holds the mirror for the block, knowing what every other turn in it has done."""
        if self._ledger is None:
            yield
            return
        with self._ledger.held(self._replay):
            yield

    def _keep(self, local_path: str, record: FileRecord) -> None:
        self._files[local_path] = record
        self._tell("file", local_path, *astuple(record))

    def _tell(self, *entry: Any) -> None:
        if self._ledger is not None:
            self._ledger.tell(list(entry))

    def _replay(self, entry: list[Any]) -> None:
        """Applies one change another turn in the mirror made to what it knows."""
        try:
            what, path, *rest = entry
            if what == "file":
                self._files[path] = FileRecord(*rest)
            elif what == "dirty":
                self._dirty_candidates.add(path)
            elif what == "forget":
                self._drop(path)
            elif what == "rename":
                self._move(path, *rest)
        except (TypeError, ValueError):
            log.debug("ignoring a journal entry %r", entry)

    def _record_local_state(self, local_path: str, record: FileRecord) -> None:
        try:
            info = os.lstat(local_path)
        except OSError:
            return
        record.local_size = info.st_size
        record.local_mtime_ns = info.st_mtime_ns


def _subtree_test(root: str) -> Callable[[str], bool]:
    """Predicate matching ``root`` and everything beneath it."""
    prefix = root.rstrip("/") + "/"
    return lambda path: path == root or path.startswith(prefix)


def _subtree_rebase(source: str, target: str) -> Callable[[str], str]:
    """Move a path from under ``source`` to the same place under ``target``."""
    return lambda path: target + path[len(source) :]


def _is_intact(local_path: str, record: FileRecord) -> bool:
    """True when the local copy still matches what we last wrote there."""
    try:
        info = os.lstat(local_path)
    except OSError:
        return False
    return (
        info.st_size == record.local_size and info.st_mtime_ns == record.local_mtime_ns
    )


def _remove_any(path: str) -> None:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.unlink(path)
    except OSError:
        log.debug("could not remove %s", path, exc_info=True)


def _unlink_quietly(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def prepare_shadow_root(path: str, *, force: bool = False, target: str = "") -> None:
    """Create or validate the local directory that mirrors the target.

    Refuses to take over a directory that already holds unrelated files, and
    refuses to re-point an existing mirror at a different target: the mirror is
    authoritative, so in both cases anything the target does not have would be
    deleted.  Previously used shadows are remembered outside the directory, in
    :data:`REGISTRY_DIR`.
    """
    record = _registry_entry(path)
    previous = _recorded_target(record)
    if previous is not None and previous != target and not force:
        raise FileExistsError(
            errno.EEXIST,
            f"{path} mirrors {previous}, not {target}. Humanize replaces this "
            "directory with the new target's contents and would delete "
            "everything only the old one has. Use a different directory, or "
            "pass --force.",
            path,
        )
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    elif not os.path.isdir(path):
        raise NotADirectoryError(errno.ENOTDIR, "shadow root is not a directory", path)
    elif not force and previous is None and any(os.scandir(path)):
        raise FileExistsError(
            errno.EEXIST,
            f"{path} already contains files and is not a Humanize mirror. "
            "Humanize replaces this directory with the target's contents and "
            "would delete them. Use an empty directory, or pass --force.",
            path,
        )
    os.makedirs(os.path.dirname(record), exist_ok=True)
    # Whole or not at all: a turn starting in this mirror reads it while another is writing
    # it, and half a record is none -- a mirror refused as somebody else's directory.
    atomic.writes(Path(record), json.dumps({"shadow": path, "target": target}))


def _recorded_target(record: str) -> str | None:
    """The target this mirror was last used against, or ``None`` if it is new."""
    try:
        with open(record, encoding="utf-8") as handle:
            return str(json.load(handle).get("target", ""))
    except (OSError, ValueError):
        return None


def _registry_entry(path: str) -> str:
    digest = hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:16]
    where = os.environ.get(SHADOWS) or REGISTRY_DIR
    return os.path.join(os.path.expanduser(where), f"{digest}.json")
