"""Stand-ins shared by the coganchor anchor tests: frames in memory, a router, a target."""

from __future__ import annotations

import errno
import io
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, BinaryIO

from hmz.coganchor.proto import Channel, Frame, Stream

if TYPE_CHECKING:
    from collections.abc import Iterable


class Kept(io.BytesIO):
    """A writer whose bytes outlive the channel closing it."""

    def close(self) -> None:
        """Keeps what was written readable."""


def names(directory: str | os.PathLike[str]) -> list[str]:
    """What a directory holds, by name and in order."""
    return sorted(one.name for one in os.scandir(directory))


def wire(frames: Iterable[Frame] = ()) -> tuple[Channel, Kept]:
    """A channel that reads `frames` and writes into the buffer handed back."""
    sent = Kept()
    return Channel(io.BytesIO(b"".join(one.encode() for one in frames)), sent), sent


def frames(blob: bytes) -> list[Frame]:
    """Every frame a buffer holds, decoded."""
    reading = Channel(io.BytesIO(blob), io.BytesIO())
    found: list[Frame] = []
    while (one := reading.recv()) is not None:
        found.append(one)
    return found


@dataclass(frozen=True)
class Layout:
    """One workspace, mirrored at `local` and named `virtual` on the target."""

    local: str
    virtual: str

    def to_virtual(self, path: str) -> str:
        return self.virtual + path[len(self.local) :]


@dataclass
class Router:
    """Routes everything under one local directory to the target, and nothing else."""

    layout: Layout

    def _inside(self, path: str) -> bool:
        return path == self.layout.local or path.startswith(self.layout.local + "/")

    def layout_for(self, path: str) -> Layout | None:
        return self.layout if self._inside(path) else None

    def is_remote_path(self, path: str) -> bool:
        return self._inside(path)

    def to_virtual(self, path: str) -> str:
        return self.layout.to_virtual(path)


@dataclass
class Entry:
    """A file, directory or link on the fake target."""

    kind: str
    body: bytes = b""
    mode: int = 0o100644
    mtime_ns: int = 1_000_000_000
    target: str = ""


@dataclass
class Target:
    """A target held in a dict of virtual paths, answering as `RemoteClient` does."""

    tree: dict[str, Entry] = field(default_factory=dict[str, Entry])
    listed: list[str] = field(default_factory=list[str])
    read: list[str] = field(default_factory=list[str])
    written: dict[str, bytes] = field(default_factory=dict[str, bytes])

    def _describe(self, name: str, entry: Entry) -> dict[str, Any]:
        said: dict[str, Any] = {
            "name": name,
            "kind": entry.kind,
            "mode": entry.mode,
            "size": len(entry.body),
            "mtime_ns": entry.mtime_ns,
        }
        if entry.kind == "link":
            said["target"] = entry.target
        return said

    def listdir(self, path: str) -> dict[str, Any]:
        self.listed.append(path)
        held = self.tree.get(path)
        if held is None:
            raise FileNotFoundError(errno.ENOENT, "gone", path)
        if held.kind != "dir":
            raise NotADirectoryError(errno.ENOTDIR, "not a directory", path)
        entries = [
            self._describe(name.rpartition("/")[2], entry)
            for name, entry in self.tree.items()
            if name.rpartition("/")[0] == path and name != path
        ]
        return {"entries": entries}

    def read_file(self, path: str, sink: BinaryIO) -> dict[str, Any]:
        self.read.append(path)
        entry = self.tree[path]
        sink.write(entry.body)
        return {"size": len(entry.body), "mtime_ns": entry.mtime_ns}

    def write_file(
        self, path: str, source: BinaryIO, mode: int | None = None
    ) -> dict[str, Any]:
        body = source.read()
        self.written[path] = body
        self.tree[path] = Entry("file", body, mode or 0o100644, 2_000_000_000)
        return {"size": len(body), "mtime_ns": 2_000_000_000}


@dataclass
class Exec:
    """What a fake client was asked to run, and the callbacks to answer it through."""

    argv: list[str]
    cwd: str
    env: dict[str, str]
    on_output: Any
    on_exit: Any
    options: dict[str, Any]
    stdin: list[bytes] = field(default_factory=list[bytes])
    closed: bool = False
    signals: list[int] = field(default_factory=list[int])

    def send_stdin(self, data: bytes) -> None:
        self.stdin.append(data)

    def close_stdin(self) -> None:
        self.closed = True

    def signal(self, signum: int) -> None:
        self.signals.append(signum)

    def answer(
        self, out: bytes = b"", *, code: int = 0, error: OSError | None = None
    ) -> None:
        """Says `out` on stdout and exits `code`, or fails with `error`."""
        if out:
            self.on_output(Stream.STDOUT, out)
        if error is not None:
            self.on_exit(None, error)
        else:
            self.on_exit({"exit_code": code}, None)
