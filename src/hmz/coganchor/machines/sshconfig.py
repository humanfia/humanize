"""The hosts an ssh config names, and what `ssh` itself makes of each.

Two questions, answered by two different readers. Which hosts a config names is read off the
file -- every `Host` line, following every `Include` -- because a name is only a name and
reading one costs nothing. What a name comes to -- the machine, the login, the port, the key,
the jump host -- is asked of `ssh -G`, which is the one reader that gets every rule of the
format right: `Match`, tokens, first-value-wins, the system-wide file. A second reader of
those would be a second answer to keep in step with the first.
"""

from __future__ import annotations

import glob
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["SSHHost", "aliases", "default", "hosts", "resolve"]

#: How deep one `Include` may name another, which is ssh's own limit.
_DEPTH = 16

#: One line of a config: a keyword, and what follows it after spaces or an `=`.
_LINE = re.compile(r"\s*([A-Za-z][A-Za-z0-9]*)(?:\s*=\s*|\s+)(.*)")

#: The keys `ssh` tries when nobody named one, which is what `ssh -G` lists for a host
#: whose config names none -- and so not a key anybody chose for it.
_DEFAULT_KEYS = frozenset(
    f"~/.ssh/{key}"
    for key in (
        "id_rsa",
        "id_ecdsa",
        "id_ecdsa_sk",
        "id_ed25519",
        "id_ed25519_sk",
        "id_xmss",
        "id_dsa",
    )
)

#: How long `ssh -G` is given, which reads files and reaches nothing.
_RESOLVING = 10.0


@dataclass(frozen=True, slots=True)
class SSHHost:
    """One host of an ssh config, as `ssh` itself resolves it.

    Attributes:
      alias: The name it was asked for by.
      host: The machine it reaches (`HostName`), which is the alias where nothing renames it.
      user: Who it logs in as.
      port: The port it dials.
      identity_files: The keys named for it, and none where it is left to ssh's own.
      proxy_jump: The host it is reached through, or "".
    """

    alias: str
    host: str
    user: str
    port: int
    identity_files: tuple[str, ...] = ()
    proxy_jump: str = ""


def default() -> Path:
    """The user's own ssh config, whether or not there is one."""
    return Path("~/.ssh/config").expanduser()


def aliases(config: str | os.PathLike[str] | None = None) -> list[str]:
    """Every host a config names, in the order it names them.

    A pattern is not a host: `Host *` is what the settings under it apply to rather than
    somewhere to go, and neither is one with `?` in it or a negation.

    Args:
      config: The config file, or None for the user's own.

    Returns:
      Each name once, following every `Include` as ssh would; nothing where there is no
      such file.
    """
    named: list[str] = []
    _read(_expanded(config) if config is not None else default(), named, 0)
    return named


def _expanded(path: str | os.PathLike[str]) -> Path:
    """A path with its `~` expanded as ssh would.

    A `~user` there is no such user for is left as it is -- a file that is not there -- rather
    than raised for, as `Path.expanduser` does.
    """
    return Path(os.path.expanduser(path))  # noqa: PTH111 -- see above


def _read(at: Path, named: list[str], depth: int) -> None:
    """Adds the hosts one file names, and those of every file it includes."""
    if depth > _DEPTH:
        return
    try:
        written = at.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in written.splitlines():
        said = _LINE.match(line)
        if said is None:
            continue  # a comment, a blank, or a keyword with nothing after it
        keyword, rest = said[1].lower(), said[2]
        try:
            words = shlex.split(rest, comments=True)
        except ValueError:
            continue  # a quote left open: ssh refuses the line, and so is it here
        if keyword == "host":
            named.extend(
                one for one in words if not set(one) & set("*?!") and one not in named
            )
        elif keyword == "include":
            for pattern in words:
                # A relative one is under `~/.ssh`, as ssh reads it in a user's config.
                path = _expanded(pattern)
                if not path.is_absolute():
                    path = default().parent / path
                # `glob.glob`, since `Path.glob` takes no pattern that is absolute.
                for one in sorted(glob.glob(str(path))):  # noqa: PTH207
                    _read(Path(one), named, depth + 1)


def resolve(
    destination: str,
    flags: Sequence[str] = (),
    *,
    alias: str = "",
    seconds: float = _RESOLVING,
) -> SSHHost:
    """What `ssh` makes of a destination, asked of `ssh -G`, which reaches nothing.

    Args:
      destination: What `ssh` would be given: an alias, a host, or `user@host`.
      flags: What else it would be told, as `-F FILE` and `-o KEYWORD=VALUE`.
      alias: What to call the answer, defaulting to the destination.
      seconds: How long `ssh -G` is given.

    Returns:
      The host it resolves to.

    Raises:
      OSError: If there is no `ssh`, or it would not say -- a config it cannot read.
    """
    try:
        said = subprocess.run(
            ["ssh", "-G", *flags, "--", destination],
            capture_output=True,
            text=True,
            timeout=seconds,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(
            f"ssh -G {destination} timed out after {seconds:g}s"
        ) from error
    if said.returncode:
        raise OSError(f"ssh -G {destination}: {said.stderr.strip() or said.returncode}")
    values: dict[str, str] = {}
    keys: list[str] = []
    for line in said.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "identityfile":
            keys.append(value)
        else:
            values.setdefault(key, value)
    port = values.get("port", "")
    jump = values.get("proxyjump", "")
    return SSHHost(
        alias=alias or destination,
        host=values.get("hostname", destination),
        user=values.get("user", ""),
        port=int(port) if port.isdigit() else 22,
        # ssh's own list is several keys; one of those named on its own was chosen.
        identity_files=()
        if len(set(keys)) > 2 and set(keys) <= _DEFAULT_KEYS  # noqa: PLR2004
        else tuple(keys),
        proxy_jump="" if jump == "none" else jump,
    )


def hosts(
    config: str | os.PathLike[str] | None = None, *, seconds: float = _RESOLVING
) -> list[SSHHost]:
    """Every host a config names, each as `ssh` resolves it under that config.

    Args:
      config: The config file, or None for the user's own.
      seconds: How long `ssh -G` is given for each.

    Returns:
      One apiece, in the order the config names them.

    Raises:
      OSError: If there is no `ssh`, or it cannot read the config.
    """
    flags = ("-F", str(_expanded(config))) if config is not None else ()
    return [
        resolve(alias, flags, alias=alias, seconds=seconds) for alias in aliases(config)
    ]
