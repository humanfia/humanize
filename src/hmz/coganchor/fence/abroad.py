"""A fence said in scope terms, for the machine an anchored turn's work lands on.

A :class:`~hmz.coganchor.fence.Fence` is paths, and paths are one machine's: the workdir a flow
names is somewhere else on a target, its home is another user's, its Python is installed
elsewhere or not at all. So what crosses to the target is not the fence but what it was drawn
from -- the three levels, whether the network is cut, and for a CLI that runs there itself the
hosts its model is at and the state it keeps under its home -- and the target draws the same
fence again around its own workdir, its own home and its own minimum. :func:`told` is the
first half, on the machine the turn is started from; :func:`drawn` is the second, in the
serving half on the target.

Shared by both halves, which is why it imports nothing but the fence itself: the serving half
may import no module of the agent half's, and this one and the fence it reads are the only
part of that rule it bends (:mod:`hmz.coganchor.serve`).
"""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from hmz.coganchor.fence import ALL, LEVELS, READ, Fence

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = ["HOME", "drawn", "installed", "ready", "told"]

#: How a path under the home is said to the target: relative to whatever home it has.
HOME: Final = "~/"


def told(fence: Fence, *, home: str, native: bool) -> dict[str, Any]:
    """What the target is told of a fence, for it to draw again around its own paths.

    Args:
      fence: The fence, as this machine drew it.
      home: This machine's home, which the paths the CLI keeps its state under are said
        relative to.
      native: Whether the CLI itself runs on the target. One supervised here runs only its
        commands there, and a command needs neither the model's hosts nor the CLI's state --
        so neither is sent, and a command at `online` NONE reaches no host at all. For one
        that runs there, every path `fence` writes under `home` is taken for the CLI's own
        state: a native CLI's fence is its levels and that state, and none of the roots its
        levels grant here, which the target grants again around its own.

    Returns:
      The levels as `local`, `user` and `system`, and `online`; for a native CLI, `hosts`, the
      state it writes under its home as `write` -- each as `~/...`, to which a caller may add
      a path of the target's own -- and `programs`, which has the target let the CLI read its
      own install tree.

    Raises:
      ValueError: If the fence was drawn path by path, and so has no levels to say.
    """
    if not fence.scopes:
        raise ValueError(
            "a fence drawn path by path cannot be drawn again on another machine"
        )
    local, user, system = fence.scopes
    said: dict[str, Any] = {
        "local": local,
        "user": user,
        "system": system,
        "online": fence.online,
    }
    if native:
        root = os.path.normpath(home)
        said["hosts"] = list(fence.hosts)
        said["write"] = [
            HOME + os.path.relpath(one, root)
            for one in fence.write
            if one.startswith(root.rstrip(os.sep) + os.sep)
        ]
        said["programs"] = True
    return said


def drawn(
    said: Mapping[str, Any],
    *,
    workdirs: Sequence[str],
    home: str,
    read: Iterable[str] = (),
    write: Iterable[str] = (),
) -> Fence:
    """The fence a target holds a command to, drawn around its own paths.

    Args:
      said: What :func:`told` said.
      workdirs: The directories the target exports, each granted as the workdir is.
      home: The home of the user the target runs commands as. One that is `/` or not there
        -- a container started as a user its image has no entry for -- is no home: the user
        scope is then nothing past the workdir, and no state is kept under it.
      read: More of the target's own paths to read.
      write: More of them to write.

    Returns:
      The fence, with the target's own minimum -- its programs, its Python, its devices.

    Raises:
      ValueError: If `said` is not a fence's levels, or names a path that is neither under
        the home nor absolute, or there is no workdir.
    """
    if not workdirs:
        raise ValueError("a fence is drawn around a workdir, and there is none")
    levels = [said.get(one) for one in ("local", "user", "system")]
    if not all(one in LEVELS for one in levels):
        raise ValueError(f"a fence's levels are each one of {', '.join(LEVELS)}")
    online = said.get("online", True)
    if not isinstance(online, bool):
        raise ValueError("a fence's online is true or false")  # noqa: TRY004
    hosts = _strings(said, "hosts")
    kept = _strings(said, "write")
    if any(
        not one.startswith((HOME, os.sep)) or ".." in one.split("/") for one in kept
    ):
        raise ValueError(
            f"a fence's own paths are said under {HOME}, or as the target's own"
        )
    homed = bool(home) and os.path.normpath(home) != os.sep and Path(home).is_dir()
    local = str(levels[0])
    first, *rest = workdirs
    widened = [*rest] if local == ALL else []
    seen = [*rest] if local == READ else []
    return Fence.of(
        local=local,
        user=str(levels[1]),
        system=str(levels[2]),
        online=online,
        workdir=first,
        home=home if homed else first,
        hosts=hosts,
        read=[*seen, *read],
        write=[
            *widened,
            *write,
            *(one for one in kept if one.startswith(os.sep)),
            *(
                str(Path(home, one[len(HOME) :]))
                for one in kept
                if homed and one.startswith(HOME)
            ),
        ],
    )


def ready(fence: Fence, home: str) -> None:
    """Makes the directories a fence lets be written under the home, where they are not yet.

    A grant of a path that is not there is no grant at all -- Landlock holds only what exists
    -- so the state a CLI keeps under its home is made before it is walled in, or a CLI that
    has never run on this machine could not make it on its first turn. Only directories, read
    off the name as the machine the turn was started from reads them: `~/.cli` is one,
    `~/.cli.json` is a file.

    Args:
      fence: The fence, as :func:`drawn` drew it.
      home: The home it was drawn around.
    """
    root = os.path.normpath(home).rstrip(os.sep) + os.sep
    for one in fence.write:
        name = Path(one).name.lstrip(".")
        if one.startswith(root) and "." not in name and not Path(one).exists():
            with contextlib.suppress(OSError):
                Path(one).mkdir(mode=0o700, parents=True, exist_ok=True)


def installed(program: str, path: str | None = None) -> list[str]:
    """What a program needs to be read for it to run: itself, and the tree it was installed as.

    The target's own answer to what the machine a CLI is started from works out for it: the
    program and the file its links lead to, and the install tree that is part of -- an npm
    package, a `bin` with a `lib` beside it, or the directory it sits in -- and the same again
    for the interpreter its first line names. Never `/` or the home themselves.

    Args:
      program: The program, as a path or a name to look up.
      path: The `PATH` to look a name up on.

    Returns:
      The paths, or nothing for a program that is not there.
    """
    found = shutil.which(program, path=path) if os.sep not in program else program
    if found is None or not Path(found).exists():
        return []
    held = [found]
    real = Path(found).resolve()
    held += _tree(real)
    try:
        with real.open("rb") as reading:
            first = reading.readline(256)
    except OSError:
        return held
    if first.startswith(b"#!"):
        words = first[2:].decode(errors="replace").split()
        if words[:1] and Path(words[0]).name == "env" and len(words) > 1:
            words = words[1:]
        if words and (interpreter := shutil.which(words[0], path=path)):
            held += [interpreter, *_tree(Path(interpreter).resolve())]
    return held


def _tree(real: Path) -> list[str]:
    """The file a program really is, and the tree it was installed as a part of."""
    never = {Path(os.sep), Path.home()}
    parts = real.parts
    if "node_modules" in parts:
        at = len(parts) - parts[::-1].index("node_modules")
        width = 2 if at < len(parts) and parts[at].startswith("@") else 1
        return [str(real), str(Path(*parts[: at + width]))]
    directory = real.parent
    if directory.name == "bin" and (directory.parent / "lib").is_dir():
        directory = directory.parent
    return [str(real)] + ([str(directory)] if directory not in never else [])


def _strings(said: Mapping[str, Any], name: str) -> list[str]:
    """A list of strings out of what was said, or a refusal of one that is not."""
    listed: object = said.get(name, [])
    if not isinstance(listed, list) or not all(
        isinstance(one, str) for one in cast("list[object]", listed)
    ):
        raise ValueError(f"a fence's {name} is a list of strings")
    return list(cast("list[str]", listed))
