"""Humanize's one settings file: everything `/settings` can set, in `settings.toml`.

One file under Humanize's own home, keyed by what each part of it is: what each workspace was
set up to run, the handful of settings that are this machine's, the chains a failed turn falls
back along (`fallbacks`), the CLIs somebody added by hand (`clis`) and the machines an
environment may be put on (`runtimes`). One file rather than one per setting, because a person
reading what Humanize was told is reading one thing, and a file per part was a directory of
them to find it in -- and because whoever writes one part has to leave every other part as it
was, which is one lock and one file to keep it on.

Here rather than above, because the parts `coganchor` keeps are written by `coganchor`: the
interface and a command line write the workspaces through :mod:`hmz.runtime.settings`, which
writes through this.

TOML rather than the YAML it once was, which a release that finds only `settings.yaml` beside
where this one is converts once (:func:`_migrates`) and leaves as `settings.yaml.migrated`.
TOML has no null, so a part set to None is a part taken out.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
import tomllib
from typing import TYPE_CHECKING, Any, cast

from hmz import home
from hmz.coganchor import atomic

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, MutableMapping
    from pathlib import Path

__all__ = ["changes", "read", "reading", "where"]

log = logging.getLogger(__name__)

#: How long, in seconds, a write waits for another writer to be done before going ahead
#: without it. A write takes milliseconds, and seconds on a disk busy enough that fsync
#: queues; this is for a writer that has stopped, not for one that is slow.
_PATIENCE = 30.0

#: The name the file had while it was YAML, and the one it is left under once converted.
_FORMER = "settings.yaml"
_MIGRATED = "settings.yaml.migrated"

#: What a key YAML read as a boolean was written as.
_KEYS = {True: "on", False: "off"}

#: Each YAML file, by where it is and when it was written, this process has tried to convert
#: and could not: tried once rather than under the lock on every read, until it is changed.
_TRIED: set[tuple[Path, int]] = set()


def where() -> Path:
    """The file, whether or not anything has been written to it."""
    return home() / "settings.toml"


def reading() -> dict[str, Any] | None:
    """Everything the file holds, and None where there is one that cannot be read as one.

    Told apart from a file that is not there, which holds nothing, because a write makes
    its change to what the file holds: one somebody left half-edited is not a reason to
    write it back as nothing but that change.
    """
    _migrates()
    return _reading()


def read() -> dict[str, Any]:
    """Everything the file holds, which is nothing at all when it cannot be read.

    A settings file that is missing, unreadable, or not what this writes is a machine with
    nothing set -- never a reason not to start.
    """
    held = reading()
    return {} if held is None else held


def changes(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Makes one change to the file, and to nothing else in it.

    Two writers are alive at once wherever a menu writes a setting while the interface goes
    on remembering flows, and wherever two `hmz` share a home -- so nothing a writer read
    earlier is written back. The file is read again under a lock, the change is made to what
    it holds now, and that is what goes back: a part some other writer changed since is still
    there afterwards, and so is every comment somebody wrote beside a part left as it was.

    The lock is a `flock` on a file beside it, which the kernel lets go of however the
    process ends. Whole and then moved into place, as every other file Humanize writes is:
    one read while it is being written is the old one or the new one and never half of each.
    A new file is this user's alone, and one already there keeps the mode it has.

    One there that cannot be read is never written over: it is most likely somebody halfway
    through correcting it by hand, and what any writer holds of it is older than what they
    have typed since.

    Args:
      change: What to do to a reading of the file, in place. A part it sets to None is
        taken out, TOML having no null.

    Returns:
      What the file holds now.

    Raises:
      OSError: If it cannot be read, or written.
      ValueError: If the change left something TOML cannot hold.
    """
    import tomlkit
    from tomlkit.exceptions import TOMLKitError

    at = where()
    _migrates()
    with _locked(at):
        kept, unread = tomlkit.document(), at
        try:
            kept = tomlkit.parse(at.read_text(encoding="utf-8"))
            held = kept.unwrap()
        except FileNotFoundError:
            held, unread = _former(at), at.with_name(_FORMER)
        except (OSError, ValueError, TOMLKitError):
            held = None
        if held is None:
            raise OSError(f"{unread} cannot be read: correct or remove it")
        change(held)
        held = _tomlable(held)
        _onto(kept, held)
        atomic.writes(at, tomlkit.dumps(kept), mode=None if at.exists() else 0o600)
    return held


def _reading() -> dict[str, Any] | None:
    """What :func:`reading` reads, without first converting a YAML file left from before.

    Where there is no TOML file yet but a YAML one that could not be converted -- a home
    nobody may write -- that one is what is read.
    """
    at = where()
    try:
        said = at.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _former(at)
    except (OSError, ValueError):
        return None
    try:
        return tomllib.loads(said)
    except tomllib.TOMLDecodeError:
        return None


def _former(at: Path) -> dict[str, Any] | None:
    """What the YAML file beside `at` holds, as TOML can hold it: {} where there is none."""
    import yaml

    try:
        said = at.with_name(_FORMER).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    try:
        held = yaml.safe_load(said)
    except yaml.YAMLError:
        return None
    if held is None:
        return {}
    return _tomlable(cast("dict[str, Any]", held)) if isinstance(held, dict) else None


def _migrates() -> None:
    """Converts the YAML file an earlier release wrote, once, where there is no TOML one yet.

    Under the lock every writer takes, so that two processes starting at once convert it
    once between them; and moved aside rather than removed, so that nothing a person wrote
    is lost to a conversion they did not ask for. One that cannot be read as YAML is left
    where it is, for them to correct -- and until they do, the file reads as unreadable.
    """
    import tomlkit

    at = where()
    former = at.with_name(_FORMER)
    if at.exists():
        return
    try:
        tried = (former, former.stat().st_mtime_ns)
    except OSError:
        return
    if tried in _TRIED:
        return
    with _locked(at):
        if at.exists():
            return  # converted by another, while this waited
        held = _former(at)
        if held is None:
            _TRIED.add(tried)
            log.warning("%s cannot be read as YAML: correct or remove it", former)
            return
        try:
            atomic.writes(at, tomlkit.dumps(held), mode=0o600)
            former.replace(at.with_name(_MIGRATED))
        except (OSError, ValueError) as why:
            _TRIED.add(tried)
            log.warning("%s could not be converted to %s: %s", former, at, why)


def _tomlable(held: Any) -> Any:
    """`held` with every None taken out and every key a string, as TOML can hold it."""
    if isinstance(held, dict):
        return {
            # YAML 1.1 read a plain `on` key, a graph's among them, as true.
            (_KEYS[key] if isinstance(key, bool) else str(key)): _tomlable(value)
            for key, value in cast("dict[Any, Any]", held).items()
            if value is not None
        }
    if isinstance(held, (list, tuple)):
        return [_tomlable(one) for one in cast("list[Any]", held) if one is not None]
    return held


def _onto(kept: MutableMapping[str, Any], held: dict[str, Any]) -> None:
    """Makes what `kept` holds `held`, leaving every part that is already so as it was.

    A part left as it was keeps the comments and the layout somebody gave it by hand.
    """
    for gone in [key for key in kept if key not in held]:
        del kept[gone]
    for key, value in held.items():
        was = kept.get(key)
        if isinstance(value, dict) and isinstance(was, dict):
            _onto(cast("MutableMapping[str, Any]", was), cast("dict[str, Any]", value))
        elif key not in kept or not _same(cast("object", was), cast("object", value)):
            kept[key] = value
    if list(kept) != list(held):
        # In the order the change left them, as a part renamed in place is.
        moved = [(key, kept[key]) for key in held]
        for key, _ in moved:
            del kept[key]
        for key, one in moved:
            kept[key] = one


def _same(was: object, value: object) -> bool:
    """Whether two values are one, telling `1` from `true` and `1` from `1.0` as TOML does."""
    # What tomlkit holds, as the plain value it is.
    plain = cast("object", getattr(was, "unwrap", lambda: was)())
    if isinstance(plain, dict) and isinstance(value, dict):
        mine, theirs = cast("dict[str, Any]", plain), cast("dict[str, Any]", value)
        return mine.keys() == theirs.keys() and all(
            _same(mine[k], theirs[k]) for k in theirs
        )
    if isinstance(plain, list) and isinstance(value, list):
        mine, theirs = cast("list[Any]", plain), cast("list[Any]", value)
        return len(mine) == len(theirs) and all(map(_same, mine, theirs))
    return type(cast("object", plain)) is type(value) and plain == value


@contextlib.contextmanager
def _locked(at: Path) -> Generator[None]:
    """Holds the lock every writer of the file takes, for as long as the block runs.

    Where it cannot be had the block runs anyway, which is a write that might meet another
    rather than one that never happens: a home that cannot be written, a lock file somebody
    else made that this cannot open, a filesystem that has no `flock`, or a writer that has
    held it for longer than anybody at an interface should wait -- one stopped with ctrl-z
    halfway through a write is holding it for as long as it is stopped.
    """
    import fcntl

    try:
        at.parent.mkdir(parents=True, exist_ok=True)
        # Read-only, which `flock` needs no more than, so that one another user made is still
        # one this can take.
        fd = os.open(
            at.with_name(f".{at.name}.lock"),
            os.O_CREAT | os.O_RDONLY | os.O_CLOEXEC,
            0o600,
        )
    except OSError:
        yield
        return
    try:
        waited = time.monotonic() + _PATIENCE
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if time.monotonic() < waited:
                    time.sleep(0.01)
                    continue
            except OSError:
                pass
            break
        yield
    finally:
        os.close(fd)  # which lets go of the lock too
