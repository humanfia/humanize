"""File handles, by which bytes cross a session a chunk at a time (`files.*`).

A session carries JSON, and a file is carried over it as chunks of at most a mebibyte, each the
base64 of its bytes (Section 6.9 of wire.md). A handle is the daemon's name for one file being
carried: a write handle is made here and filled, and given to the method that takes the file
(`runs.import`); a read handle is answered by the method that made the file (`runs.bundle`) and
read here. :meth:`Files.upload` and :meth:`Files.download` are the two loops, which is all most
programs want of this family.
"""

from __future__ import annotations

import base64
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final

from . import Family

if TYPE_CHECKING:
    import os

__all__ = ["CHUNK", "Chunk", "Files"]

#: The most bytes one chunk carries, either way.
CHUNK: Final = 1 << 20


@dataclass(frozen=True)
class Chunk:
    """Some bytes of a file being read."""

    data: bytes
    """The bytes, from the offset asked for."""
    eof: bool
    """Whether they reach the end of the file."""


class Files(Family):
    """File handles, by which bytes cross a session a chunk at a time."""

    METHODS: ClassVar = ("files.create", "files.write", "files.read", "files.close")

    def create(self, name: str, size: int) -> str:
        """Makes a write handle for a file about to be sent.

        Args:
          name: The file's name, with no directory.
          size: How many bytes it is, at most 2 147 483 648.

        Returns:
          The handle, which is this session's and ends with it.
        """
        return str(self._call("files.create", name=name, size=size)["handle"])

    def write(self, handle: str, offset: int, data: bytes) -> int:
        """Appends a chunk to a write handle.

        Args:
          handle: The handle.
          offset: How many bytes were written before this, which is where these go.
          data: The bytes, at most `CHUNK` of them.

        Returns:
          How many bytes the handle holds now.

        Raises:
          hmz.sdk.Refused: 409 for another offset than the length written so far, 413 for
            bytes past the size declared, 404 for a handle that is not open.
        """
        said = self._call(
            "files.write",
            handle=handle,
            offset=offset,
            data=base64.b64encode(data).decode("ascii"),
        )
        return int(said["size"])

    def read(self, handle: str, offset: int, length: int = CHUNK) -> Chunk:
        """Reads a chunk of a read handle.

        Args:
          handle: The handle.
          offset: Where in the file to read from.
          length: How many bytes to read at most, at most `CHUNK`.

        Raises:
          hmz.sdk.Refused: 404 for a handle that is not open.
        """
        said = self._call("files.read", handle=handle, offset=offset, length=length)
        return Chunk(base64.b64decode(said["data"]), bool(said["eof"]))

    def close(self, handle: str) -> None:
        """Ends a handle, and removes what it held from the daemon's machine.

        Raises:
          hmz.sdk.Refused: 404 for a handle that is not open.
        """
        self._call("files.close", handle=handle)

    def upload(self, path: str | os.PathLike[str], *, name: str | None = None) -> str:
        """Sends one file of this machine to the daemon, a chunk at a time.

        Args:
          path: The file.
          name: What the daemon is told it is called, its own name where None.

        Returns:
          A write handle holding the whole file, for the method that takes it. A method that
          takes it ends it; otherwise it is the caller's to :meth:`close`.

        Raises:
          OSError: If the file cannot be read.
          hmz.sdk.Refused: If the daemon refused it: 413 for one that is too large.
        """
        at = Path(path)
        with at.open("rb") as file:
            size = at.stat().st_size
            handle = self.create(name or at.name, size)
            try:
                sent = 0
                # Never past the size declared: a file still being written is sent as it was.
                while sent < size and (chunk := file.read(min(CHUNK, size - sent))):
                    sent = self.write(handle, sent, chunk)
            except BaseException:
                self._forgets(handle)
                raise
        return handle

    def download(self, handle: str, to: str | os.PathLike[str]) -> int:
        """Reads the whole file of a read handle into a file of this machine, and ends the handle.

        It is written beside where it goes and moved there whole, so a download that stops
        halfway leaves nothing at `to`, and a file already there is replaced.

        Args:
          handle: The handle, as the method that made the file answered it.
          to: The file to write.

        Returns:
          How many bytes were written.

        Raises:
          OSError: If the file cannot be written, or the daemon sent nothing where more was
            to come.
          hmz.sdk.Refused: If the daemon refused a read.
        """
        at = Path(to)
        beside = at.with_name(f".{at.name}.new")
        written = 0
        try:
            with beside.open("wb") as file:
                while True:
                    chunk = self.read(handle, written)
                    written += file.write(chunk.data)
                    if chunk.eof:
                        break
                    if not chunk.data:
                        raise OSError(f"the daemon sent nothing more of {at.name}")
            beside.replace(at)
        finally:
            beside.unlink(missing_ok=True)
            self._forgets(handle)
        return written

    def _forgets(self, handle: str) -> None:
        """Ends a handle that may have ended already, over a session that may have too."""
        with contextlib.suppress(OSError, ValueError, TimeoutError):
            self.close(handle)
