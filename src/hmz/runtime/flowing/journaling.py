"""What a resumable run writes down as it goes, and how a resumed one picks it back up.

A run whose flow is resumable keeps one journal: a file of JSON lines, appended to and never
rewritten while the run goes. Each line is one record::

    {"t": "journal", "v": 1}
    {"t": "call", "id": 7, "parent": 3, "digest": "…", "seq": 0, "ref": "humanize1:rlcr"}
    {"t": "set", "id": 7, "key": "round", "value": 2}
    {"t": "del", "id": 7, "key": "draft"}
    {"t": "session", "id": 7, "role": "builder", "harness": "claude", "session": "…"}
    {"t": "tmp", "id": 7, "env": "workspace", "kind": "temp_clone", "name": "try-1",
     "chain": "local@/repo#temp_clone(try-1)"}
    {"t": "end", "id": 7, "ok": true}

A `call` is one flow call: its parent's id (0 for the flow at the top), the digest of what it
was called with, and `seq` -- how many calls under the same parent with the same digest came
before it. That pair is what a resumed run matches a call against: the flow at the top picks
up unconditionally, and a call under a flow that picked up picks up the earlier call with its
digest and the lowest `seq` nobody has claimed yet, so a loop calling the same subflow the
same way three times picks up the three of them in order, and a gather of identical calls
picks up one apiece.

A state write is flushed as it is made: it is what the flow will read back, and a run killed
the moment after it must still have it. Everything else is batched -- written within a tenth
of a second, or with the next state write, whichever comes first -- which is what keeps a run
of ten thousand calls from being ten thousand writes. The file is synced when the run ends.

Resuming rewrites the journal once, compacted: every call, the state it ended with, its end,
its sessions and its temporary directories, and nothing of how the state got there.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pydantic_core

from hmz.flows import StateNotSerializable

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["FlowStateImpl", "Journal", "Past", "digest"]

log = logging.getLogger(__name__)

#: The journal format, written as its first line.
VERSION = 1

#: How long a record other than a state write may wait to be written, in seconds.
BATCH = 0.1


def digest(ref: str, task: str, roles: list[str], params: bytes) -> str:
    """What one flow call was called with, as a key a resumed run matches it by.

    Args:
      ref: The callee's canonical ref.
      task: The task.
      roles: One `role=spec` apiece, agents then environments, each sorted by role: an
        agent by its harness, account, model, effort, permission and skills; an environment
        by how it was derived from the one a command line named, never by a path a temporary
        copy happened to land at.
      params: The params, serialized.

    Returns:
      A hex digest.
    """
    said = "\0".join((ref, task, *roles)).encode(errors="surrogatepass")
    return hashlib.blake2b(said + b"\0" + params, digest_size=16).hexdigest()


@dataclass(slots=True)
class _Kept:
    """One call as a journal left it."""

    id: int
    parent: int
    digest: str
    seq: int
    ref: str
    state: dict[str, Any] = field(default_factory=dict[str, Any])
    ended: bool | None = None
    extra: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


@dataclass(slots=True)
class Past:
    """What an earlier run left in its journal, as a resumed run matches calls against it.

    Attributes:
      root: The id of the call at the top, or None for a journal with none.
      calls: Every call, by id.
      under: The calls under each parent with each digest, by `seq`.
    """

    root: int | None = None
    calls: dict[int, _Kept] = field(default_factory=dict[int, _Kept])
    under: dict[tuple[int, str], dict[int, int]] = field(
        default_factory=dict[tuple[int, str], dict[int, int]]
    )

    @property
    def next_id(self) -> int:
        """The first id no call of the earlier run had."""
        return max(self.calls, default=0) + 1

    def claim(self, parent: int, said: str, seq: int) -> _Kept | None:
        """The earlier call under `parent` with this digest and `seq`, if there was one."""
        found = self.under.get((parent, said))
        if found is None:
            return None
        kept = found.get(seq)
        return None if kept is None else self.calls[kept]


def _lines(path: Path) -> Iterator[dict[str, Any]]:
    """Every record a journal holds, skipping any a killed run left half-written."""
    with path.open("rb") as reading:
        for line in reading:
            try:
                said = json.loads(line)
            except ValueError:
                continue
            if isinstance(said, dict):
                yield said


def _read(path: Path) -> Past:
    """What a journal holds, replayed."""
    past = Past()
    for said in _lines(path):
        kind = said.get("t")
        try:
            if kind == "call":
                kept = _Kept(
                    int(said["id"]),
                    int(said["parent"]),
                    str(said["digest"]),
                    int(said["seq"]),
                    str(said.get("ref", "")),
                )
                past.calls[kept.id] = kept
                past.under.setdefault((kept.parent, kept.digest), {})[kept.seq] = (
                    kept.id
                )
                if kept.parent == 0 and past.root is None:
                    past.root = kept.id
                continue
            kept = past.calls.get(int(said["id"]))
            if kept is None:
                continue
            if kind == "set":
                kept.state[str(said["key"])] = said["value"]
            elif kind == "del":
                kept.state.pop(str(said["key"]), None)
            elif kind == "end":
                kept.ended = bool(said.get("ok", True))
            elif kind in ("session", "tmp"):
                kept.extra.append(said)
        except (KeyError, TypeError, ValueError):
            continue
    return past


def _dumped(value: Any) -> bytes:
    """A value as JSON, the way a state write is written.

    Raises:
      StateNotSerializable: For anything JSON has no shape for.
    """
    try:
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=True
        ).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise StateNotSerializable(
            f"{type(value).__name__} cannot be kept in a flow's state: {error}"
        ) from error


class Journal:
    """One run's journal, open for appending.

    Everything is called on the engine's loop.

    Attributes:
      path: Where it is.
      records: How many records have been appended, which a test counts.
      writes: How many times the file has been written to.
    """

    __slots__ = ("_buffer", "_fd", "_loop", "_timer", "path", "records", "writes")

    def __init__(self, path: Path, loop: asyncio.AbstractEventLoop, fd: int) -> None:
        """Takes a journal opened by :meth:`opened`."""
        self.path = path
        self._loop = loop
        self._fd = fd
        self._buffer: list[bytes] = []
        self._timer: asyncio.TimerHandle | None = None
        self.records = 0
        self.writes = 0

    @classmethod
    def opened(
        cls, path: Path, loop: asyncio.AbstractEventLoop, *, resume: bool
    ) -> tuple[Journal, Past | None]:
        """Opens a run's journal: afresh, or compacted to pick up the run it holds.

        Args:
          path: Where it is, or is to be.
          loop: The engine's loop, which batched records are written from.
          resume: Whether to pick up what is there rather than start over.

        Returns:
          The journal, and what the earlier run left in it -- None where there was nothing
          to pick up.
        """
        past = _read(path) if resume and path.is_file() else None
        if past is not None and past.root is None:
            past = None
        path.parent.mkdir(parents=True, exist_ok=True)
        beside = path.with_name(f".{path.name}.new")
        with beside.open("wb") as writing:
            writing.write(_header())
            if past is not None:
                writing.writelines(_compacted(past))
            writing.flush()
            os.fsync(writing.fileno())
        beside.replace(path)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND)
        return cls(path, loop, fd), past

    # ------------------------------------------------------------------- the records

    def call(self, jid: int, parent: int, said: str, seq: int, ref: bytes) -> None:
        """Writes down a call, batched. `ref` is already JSON."""
        self._batched(
            b'{"t":"call","id":%d,"parent":%d,"digest":"%s","seq":%d,"ref":%s}\n'
            % (jid, parent, said.encode(), seq, ref)
        )

    def end(self, jid: int, *, ok: bool) -> None:
        """Writes down that a call ended, batched."""
        self._batched(
            b'{"t":"end","id":%d,"ok":%s}\n' % (jid, b"true" if ok else b"false")
        )

    def set(self, jid: int, key: str, value: bytes) -> None:
        """Writes down a state write, now. `value` is already JSON."""
        self._buffer.append(
            b'{"t":"set","id":%d,"key":%s,"value":%s}\n'
            % (jid, pydantic_core.to_json(key), value)
        )
        self.records += 1
        self.flush()

    def delete(self, jid: int, key: str) -> None:
        """Writes down a state key forgotten, now."""
        self._buffer.append(
            b'{"t":"del","id":%d,"key":%s}\n' % (jid, pydantic_core.to_json(key))
        )
        self.records += 1
        self.flush()

    def note(self, record: dict[str, Any]) -> None:
        """Writes down a session or a temporary directory, batched."""
        self._batched(pydantic_core.to_json(record) + b"\n")

    def _batched(self, line: bytes) -> None:
        buffer = self._buffer
        buffer.append(line)
        self.records += 1
        if self._timer is None:
            self._timer = self._loop.call_later(BATCH, self.flush)

    def flush(self) -> None:
        """Writes whatever is waiting, in the order it was written down."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if not self._buffer or self._fd < 0:
            return
        data = memoryview(b"".join(self._buffer))
        self._buffer.clear()
        try:
            while data:
                data = data[os.write(self._fd, data) :]
                self.writes += 1
        except OSError:
            # A journal that can no longer be written is a run that can no longer be
            # picked up, which is worse than one that could, and better than one stopped.
            log.exception("the journal at %s could not be written", self.path)

    def close(self) -> None:
        """Writes what is waiting, syncs the file, and closes it. Idempotent."""
        self.flush()
        if self._fd < 0:
            return
        fd, self._fd = self._fd, -1
        with contextlib.suppress(OSError):
            os.fsync(fd)
        os.close(fd)


def _header() -> bytes:
    return b'{"t":"journal","v":%d}\n' % VERSION


def _compacted(past: Past) -> Iterator[bytes]:
    """An earlier run's journal, as the fewest records that say the same."""
    for jid in sorted(past.calls):
        kept = past.calls[jid]
        yield (
            b'{"t":"call","id":%d,"parent":%d,"digest":"%s","seq":%d,"ref":%s}\n'
            % (
                kept.id,
                kept.parent,
                kept.digest.encode(),
                kept.seq,
                pydantic_core.to_json(kept.ref),
            )
        )
        for key, value in kept.state.items():
            yield (
                b'{"t":"set","id":%d,"key":%s,"value":%s}\n'
                % (kept.id, pydantic_core.to_json(key), _dumped(value))
            )
        for record in kept.extra:
            yield pydantic_core.to_json(record) + b"\n"
        if kept.ended is not None:
            yield b'{"t":"end","id":%d,"ok":%s}\n' % (
                kept.id,
                b"true" if kept.ended else b"false",
            )


class FlowStateImpl:
    """A resumable flow's `FlowState`: a mapping of JSON values, each write kept as made.

    A value is kept as JSON would give it back -- a tuple as a list, a key of a dict as a
    string -- so a flow reads the same thing from a fresh run as from a resumed one; and
    what is kept is a copy, so changing the value written afterwards changes nothing kept.
    Without a journal -- a resumable flow in a run that is not -- it is kept in memory only.
    """

    __slots__ = ("_held", "_jid", "_journal")

    def __init__(self, held: dict[str, Any], journal: Journal | None, jid: int) -> None:
        """Holds a flow's state, written down against its call in a journal, if any."""
        self._held = held
        self._journal = journal
        self._jid = jid

    def __getitem__(self, key: str) -> Any:
        return self._held[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if not isinstance(key, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise StateNotSerializable(f"a state key is a string, not {key!r}")
        said = _dumped(value)
        self._held[key] = json.loads(said)
        if self._journal is not None:
            self._journal.set(self._jid, key, said)

    def __delitem__(self, key: str) -> None:
        del self._held[key]
        if self._journal is not None:
            self._journal.delete(self._jid, key)

    def __contains__(self, key: object) -> bool:
        return key in self._held

    def __iter__(self) -> Iterator[str]:
        return iter(self._held)

    def __len__(self) -> int:
        return len(self._held)

    def get(self, key: str, default: Any = None) -> Any:
        """The value kept under `key`, or `default`."""
        return self._held.get(key, default)

    def __repr__(self) -> str:
        return f"FlowState({self._held!r})"
