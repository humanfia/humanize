"""Files carried in chunks over a session: `files.*` (Section 6.9 of wire.md).

A file too big for one frame goes as a handle and the chunks read or written through it, each
at most 1 MiB, base64 in the JSON. A read handle is made by the method that answers one --
`runs.bundle`, through :func:`reading` -- and a write handle by `files.create`, whose bytes the
method it is given to takes with :func:`taken`. Either belongs to the session that made it,
and is gone, with what it held on disk, once that session ends, once `files.close` names it,
once it has gone 600 seconds unused, or once the method it was given to has taken it.

What a handle holds outlives the call that made it, so the handles open are kept here, one
registry for the daemon, each handle keyed to its session: another session naming it is told
there is no such file.
"""

from __future__ import annotations

import base64
import binascii
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.rpc import Call, Handler, Peer

__all__ = ["CHUNK", "LARGEST", "METHODS", "reading", "taken"]

#: The most bytes one chunk carries, read or written.
CHUNK = 1 << 20

#: The most bytes a write handle may be made for.
LARGEST = 1 << 31

#: How long a handle nobody uses is kept, in seconds.
_UNUSED = 600.0

#: How often the handles open are looked over for one gone unused, in seconds.
_LOOKING = 30.0

#: What the bytes of a write handle are written to, in its directory, until they are taken.
_BYTES = "bytes"


@dataclass
class _Open:
    """One handle open, and what it holds.

    Attributes:
      peer: The session it belongs to.
      path: The file it reads, or the one its bytes are written to.
      size: The file's length: as it is, of a read handle; as declared, of a write one.
      writes: Whether it is a write handle, which `files.write` writes and a method takes,
        rather than a read handle, which `files.read` reads.
      name: The file's name, as `files.create` was told it; "" for a read handle.
      written: How many bytes have been written, of a write handle.
      used: When it was last used, on the monotonic clock.
      lock: Held while it is read or written, so that two chunks never interleave.
    """

    peer: Peer
    path: Path
    size: int
    writes: bool = False
    name: str = ""
    written: int = 0
    used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)


_lock = threading.Lock()
#: Every handle open, by the text that names it.
_open: dict[str, _Open] = {}
#: The sessions told to end their handles as they close.
_watched: set[int] = set()
#: Whether handles are being looked over for one gone unused.
_looking = False


def reading(peer: Peer, path: Path) -> str:
    """Makes a read handle of a file, the file and its directory the handle's own.

    The directory the file is in is removed with the handle: give it a directory of its own.

    Args:
      peer: The session it belongs to.
      path: The file.

    Returns:
      The handle.
    """
    return _made(_Open(peer, path, path.stat().st_size))


def taken(call: Call, handle: str) -> tuple[str, Path]:
    """Takes a write handle, whole, for the method it was given to.

    No call names the handle again: the method removes the directory its bytes are in once it
    has answered, however that went. One not whole is taken all the same, and removed here.

    Args:
      call: The call it was given to.
      handle: The handle.

    Returns:
      The file's name as `files.create` was told it, and where its bytes are, alone in a
      directory of their own.

    Raises:
      RpcError: 404 where the session has no such write handle open, 409 where fewer
        bytes have been written than were declared.
    """
    one = _found(call, handle, writes=True)
    with one.lock:
        _still(handle, one, drop=True)
        if one.written < one.size:
            shutil.rmtree(one.path.parent, ignore_errors=True)
            raise RpcError(Code.CONFLICT, "The file is not whole yet.")
    return one.name, one.path


def _create(call: Call) -> dict[str, Any]:
    from hmz import machine

    name: str = call.params["name"]
    size: int = call.params["size"]
    if not 0 <= size <= LARGEST:
        raise RpcError(
            Code.INVALID_PARAMS,
            f"files.create takes size as integer from 0 to {LARGEST}.",
        )
    at = Path(tempfile.mkdtemp(dir=machine())) / _BYTES
    at.touch(mode=0o600)
    return {"handle": _made(_Open(call.peer, at, size, writes=True, name=name))}


def _write(call: Call) -> dict[str, Any]:
    offset: int = call.params["offset"]
    try:
        data = base64.b64decode(call.params["data"], validate=True)
    except (binascii.Error, ValueError) as why:
        raise RpcError(Code.REFUSED, "data is not base64.") from why
    if len(data) > CHUNK:
        raise RpcError(Code.TOO_LARGE, "That is more than a call here may carry.")
    handle: str = call.params["handle"]
    one = _found(call, handle, writes=True)
    with one.lock:
        _still(handle, one)
        if offset != one.written:
            raise RpcError(Code.CONFLICT, f"Write at {one.written}.")
        if one.written + len(data) > one.size:
            raise RpcError(
                Code.TOO_LARGE, f"That is more than the {one.size} bytes declared."
            )
        with one.path.open("ab") as writing:
            writing.write(data)
        one.written += len(data)
        return {"size": one.written}


def _read(call: Call) -> dict[str, Any]:
    offset: int = call.params["offset"]
    length: int = call.params["length"]
    if not 1 <= length <= CHUNK:
        raise RpcError(
            Code.INVALID_PARAMS,
            f"files.read takes length as integer from 1 to {CHUNK}.",
        )
    if offset < 0:
        raise RpcError(
            Code.INVALID_PARAMS, "files.read takes offset as integer from 0."
        )
    handle: str = call.params["handle"]
    one = _found(call, handle, writes=False)
    with one.lock:
        _still(handle, one)
        with one.path.open("rb") as reading:
            reading.seek(offset)
            data = reading.read(length)
    return {
        "data": base64.b64encode(data).decode("ascii"),
        "eof": offset + len(data) >= one.size,
    }


def _close(call: Call) -> dict[str, Any]:
    handle: str = call.params["handle"]
    _found(call, handle, writes=None)
    _end(handle, call.peer)
    return {}


def _end(handle: str, peer: Peer) -> None:
    """Ends a handle of a session's, once whatever is reading or writing it is done."""
    with _lock:
        one = _open.get(handle)
        if one is None or one.peer is not peer:
            return
        del _open[handle]
    with one.lock:
        shutil.rmtree(one.path.parent, ignore_errors=True)


def _still(handle: str, one: _Open, *, drop: bool = False) -> None:
    """Refuses a handle ended since it was found, and takes it out of those open on `drop`.

    Raises:
      RpcError: 404 where it has ended.
    """
    with _lock:
        if _open.get(handle) is not one:
            raise RpcError(Code.NOT_FOUND, f"There is no file {handle}.")
        if drop:
            del _open[handle]


def _made(one: _Open) -> str:
    """Opens a handle, ended with its session, and looked over until it is used no more."""
    handle = secrets.token_urlsafe(16)
    peer = one.peer
    with _lock:
        _open[handle] = one
        told = id(peer) not in _watched
        _watched.add(id(peer))
        global _looking  # noqa: PLW0603 -- the one sweeper there is, started once wanted
        looks = not _looking
        _looking = True
    if told:
        peer.closing(lambda: _closed(peer))
    if looks:
        threading.Thread(target=_sweep, daemon=True, name="hmz-files").start()
    return handle


def _found(call: Call, handle: str, *, writes: bool | None) -> _Open:
    """A handle the session has open, of the kind asked for, marked used now.

    Raises:
      RpcError: 404 where it has none such.
    """
    _expire(time.monotonic())
    with _lock:
        one = _open.get(handle)
        if (
            one is None
            or one.peer is not call.peer
            or (writes is not None and one.writes != writes)
        ):
            raise RpcError(Code.NOT_FOUND, f"There is no file {handle}.")
        one.used = time.monotonic()
        return one


def _expire(now: float) -> None:
    """Ends every handle gone unused too long."""
    with _lock:
        gone = [(h, one) for h, one in _open.items() if now - one.used > _UNUSED]
    for handle, one in gone:
        _end(handle, one.peer)


def _closed(peer: Peer) -> None:
    """Ends every handle of a session that has closed."""
    with _lock:
        _watched.discard(id(peer))
        gone = [h for h, one in _open.items() if one.peer is peer]
    for handle in gone:
        _end(handle, peer)


def _sweep() -> None:
    """Ends each handle gone unused too long, for as long as any is open."""
    global _looking  # noqa: PLW0603 -- the one sweeper there is, gone once nothing is open
    while True:
        time.sleep(_LOOKING)
        _expire(time.monotonic())
        with _lock:
            if not _open:
                _looking = False
                return


#: The methods of `files.*`.
METHODS: Mapping[str, Handler] = {
    "files.create": _create,
    "files.write": _write,
    "files.read": _read,
    "files.close": _close,
}
