"""`paths.*`: the directories of the daemon's machine, as a client browses and completes them.

What a client offers under a directory being written -- an environment's own there, or where an
epic is to work: one directory listed, and every directory a path typed could become, `~` the
home it names. Names and nothing more: no file is read.

A directory of another machine is listed too, where `paths.list` names the runtime it is on
(`env`): the host of a saved ssh runtime, asked over ssh. A runtime whose directories are this
machine's -- docker's default here, this Mac's Apple containers -- is listed as this machine
is; any other is refused, its directories being written rather than browsed.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.rpc import Call, Handler

__all__ = ["METHODS", "completed", "listed", "listed_there"]

#: The most a client is offered at once: past it, typing more says which.
_MOST = 50

#: The most entries of one directory a client is handed.
_LISTED = 500


def completed(typed: str) -> list[str]:
    """Every directory the path typed could become, written as it was typed.

    Args:
      typed: A path being written, `~` and all; "" for the home directory's own.

    Returns:
      Each directory it could become, sorted, those starting with a dot only where a dot was
      typed, at most the first fifty -- each spelled as it was typed, a `~` kept a `~`, and
      ending in the separator it would go on with.
    """
    said = typed or "~/"
    spelled, name = os.path.split(said)
    try:
        found = sorted(
            one.name
            for one in os.scandir(Path(spelled or ".").expanduser())
            if one.name.startswith(name)
            and (name.startswith(".") or not one.name.startswith("."))
            and one.is_dir()
        )
    except (OSError, RuntimeError):  # RuntimeError: the home of a user there is not
        return []
    lead = spelled if not spelled or spelled.endswith(os.sep) else spelled + os.sep
    return [f"{lead}{one}{os.sep}" for one in found[:_MOST]]


def listed(at: str, *, files: bool, hidden: bool) -> dict[str, Any]:
    """What is in one directory, as a client's file browser lists it.

    Args:
      at: The directory, `~` and all; "" for the home directory.
      files: Whether files are listed beside directories.
      hidden: Whether what starts with a dot is listed.

    Returns:
      The directory as it is shown, `~` for the home directory, and whole; the one above it,
      or "" at the top; and what is in it, directories first, each by name and whether it is
      a directory -- at most five hundred, and how many more there were.

    Raises:
      RpcError: 404, if it is not a directory there is.
    """
    home = Path.home()
    try:
        whole = (home / Path(at or "~").expanduser()).resolve()
        found = list(os.scandir(whole))
    except (OSError, RuntimeError) as why:  # RuntimeError: as in `completed`
        raise RpcError(
            Code.NOT_FOUND,
            f"{at or '~'} cannot be read: {getattr(why, 'strerror', None) or why}",
        ) from why
    kept = sorted(
        (
            (one.name, _directory(one))
            for one in found
            if hidden or not one.name.startswith(".")
        ),
        key=lambda one: (not one[1], one[0].casefold()),
    )
    entries = [{"name": name, "dir": directory} for name, directory in kept]
    if not files:
        entries = [one for one in entries if one["dir"]]
    return {
        "at": _spelled(whole, home),
        "whole": str(whole),
        "up": _spelled(whole.parent, home) if whole.parent != whole else "",
        "entries": entries[:_LISTED],
        "more": max(0, len(entries) - _LISTED),
    }


def listed_there(env: str, at: str, *, files: bool, hidden: bool) -> dict[str, Any]:
    """What is in one directory of a runtime's machine, as :func:`listed` answers it.

    Args:
      env: The runtime, as `-e` spells one with no directory: `ssh@<name>`, `docker`,
        `apple-container@<name>` and so on; `local` or "" for this machine.
      at: The directory there, absolute or from `~`; "" for the home directory.
      files: Whether files are listed beside directories.
      hidden: Whether what starts with a dot is listed.

    Raises:
      RpcError: 400 for what names no runtime; 404 for a directory that cannot be read;
        409 for a runtime whose directories cannot be listed from here, or reached.
    """
    from hmz.runtime.doing import envs

    try:
        there = envs.browsed(env, at)
    except envs.EnvRefusal as refused:
        raise RpcError(Code(refused.code), refused.why) from refused
    if there is None:
        return listed(at, files=files, hidden=hidden)
    whole, found = there
    kept = sorted(
        ((name, directory) for name, directory in found if hidden or name[:1] != "."),
        key=lambda one: (not one[1], one[0].casefold()),
    )
    entries = [{"name": name, "dir": directory} for name, directory in kept]
    if not files:
        entries = [one for one in entries if one["dir"]]
    up = "" if whole == "/" else str(PurePosixPath(whole).parent)
    return {
        "at": whole,
        "whole": whole,
        "up": up,
        "entries": entries[:_LISTED],
        "more": max(0, len(entries) - _LISTED),
    }


def _directory(one: os.DirEntry[str]) -> bool:
    try:
        return one.is_dir()
    except OSError:
        return False


def _spelled(at: Path, home: Path) -> str:
    """A directory as a person writes it: under the home directory, from `~`."""
    if at == home:
        return "~"
    if at.is_relative_to(home):
        return f"~/{at.relative_to(home).as_posix()}"
    return str(at)


def _list(call: Call) -> dict[str, Any]:
    said = call.params
    if said.get("env"):
        return listed_there(
            str(said["env"]),
            said.get("at", ""),
            files=said.get("files", False),
            hidden=said.get("hidden", False),
        )
    return listed(
        said.get("at", ""),
        files=said.get("files", False),
        hidden=said.get("hidden", False),
    )


def _complete(call: Call) -> dict[str, Any]:
    return {"paths": completed(call.params["typed"])}


#: Each method of the family, by name.
METHODS: Mapping[str, Handler] = {"paths.list": _list, "paths.complete": _complete}
