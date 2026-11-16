"""Where `coganchor` is: the anchor, as one program built from `crates/coganchor`.

The anchor is being ported from this package to Rust, unit by unit, and until the port is
whole the Python halves still run by default. `HUMANIZE_COGANCHOR` naming a built binary
switches `hmz internal anchor`, `hmz internal fence` and `hmz internal cred` over to it, which
is how the port is tested against the suites that test the Python halves.

Once it is whole, the wheel carries a build for every platform a target can be, under
`bin/<os>-<arch>/coganchor` beside this module, and :func:`found` is what reaches it.

Whether the layers that launch the anchor -- the `hmz internal anchor` line a turn is spawned
as, the serving half shipped to a target, the `cred` and `fence` wrappers -- start this program
rather than the Python halves is :func:`active`, and nothing else: it is the one line to change
when the Python halves go.
"""

from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path

__all__ = [
    "BINARIES",
    "VARIABLE",
    "active",
    "chosen",
    "digest",
    "found",
    "here",
    "named",
    "packaged",
    "shelf",
    "shipped",
    "translated",
]

#: The variable naming a built `coganchor` to run instead of the Python halves.
VARIABLE = "HUMANIZE_COGANCHOR"

#: The variable telling a `coganchor` where the builds for other platforms are, so that one
#: running here can ship the right one to a target: `<it>/<os>-<arch>/coganchor`.
BINARIES = "COGANCHOR_BINARIES"

#: The Rust target each `<os>-<arch>` is built for: static against musl, on Linux.
_TRIPLES = {
    "linux-x86_64": "x86_64-unknown-linux-musl",
    "linux-aarch64": "aarch64-unknown-linux-musl",
    "darwin-x86_64": "x86_64-apple-darwin",
    "darwin-aarch64": "aarch64-apple-darwin",
}

#: How many hex digits of a build's SHA-256 name it on a target.
_DIGEST = 16

#: The spellings `uname -m` and `platform.machine()` give for the two architectures built.
_MACHINES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}


def named(system: str, machine: str) -> str | None:
    """The directory under `bin/` holding the build for a machine, as `uname -sm` names it.

    Args:
      system: `uname -s`, or `platform.system()`: `Linux` or `Darwin`, in any case.
      machine: `uname -m`, or `platform.machine()`.

    Returns:
      `<os>-<arch>`, such as `linux-x86_64`, or None for a machine nothing is built for.
    """
    os_name = system.strip().lower()
    arch = _MACHINES.get(machine.strip().lower())
    if os_name not in ("linux", "darwin") or arch is None:
        return None
    return f"{os_name}-{arch}"


def packaged(system: str, machine: str) -> Path | None:
    """The build the wheel carries for a machine, if it carries one.

    Args:
      system: As :func:`named` takes it.
      machine: As :func:`named` takes it.

    Returns:
      Its path, or None.
    """
    where = named(system, machine)
    if where is None:
        return None
    path = Path(__file__).parent / "bin" / where / "coganchor"
    return path if path.is_file() else None


def found() -> Path | None:
    """The `coganchor` this machine runs.

    The one `HUMANIZE_COGANCHOR` names, else the wheel's build for this machine, else a build
    in this checkout's `crates/coganchor/target`.

    Returns:
      Its path, or None where there is none.
    """
    if (path := chosen()) is not None:
        return path
    if (path := packaged(platform.system(), platform.machine())) is not None:
        return path
    crate = Path(__file__).resolve().parents[3] / "crates" / "coganchor" / "target"
    for profile in ("release", "debug"):
        if (path := crate / profile / "coganchor").is_file():
            return path
    return None


def active() -> bool:
    """Whether the anchor is launched as `coganchor` rather than as the Python halves.

    While the port is under way, only where `HUMANIZE_COGANCHOR` names a build. Once it is
    whole, this answers True and the Python halves' launching goes; nothing else that launches
    the anchor asks anything but this.

    Returns:
      True where every line that starts the anchor, here or on a target, starts `coganchor`.
    """
    return chosen() is not None


def shelf() -> Path:
    """The directory the wheel carries a build for each platform in, as `<os>-<arch>/coganchor`.

    Returns:
      Its path, whether or not this install carries any.
    """
    return Path(__file__).parent / "bin"


def here() -> Path:
    """The `coganchor` this machine runs, for a line started here.

    Every process started by such a line inherits :data:`BINARIES`, set where nobody set it
    first: a harness started here ships the anchor on to its target itself, and may only find
    the build for that target's platform on this shelf.

    Returns:
      Its path, as :func:`found` says it.

    Raises:
      FileNotFoundError: Where there is no build for this machine.
    """
    path = found()
    if path is None:
        raise FileNotFoundError(
            f"no coganchor is built for this machine "
            f"({named(platform.system(), platform.machine()) or platform.machine()}); "
            f"build crates/coganchor or set {VARIABLE}"
        )
    os.environ.setdefault(BINARIES, str(shelf()))
    return path


def shipped(system: str, machine: str) -> Path | None:
    """The build to put on a machine, as its `uname -sm` names it.

    This machine's own where the target is the same OS and architecture -- which is the one
    :func:`found` reaches, and so the one `HUMANIZE_COGANCHOR` names while it names one -- and
    otherwise the wheel's, else one cross-built in this checkout's `crates/coganchor/target`
    for that machine's Rust target, as `cargo zigbuild --target` leaves it.

    Args:
      system: As :func:`named` takes it.
      machine: As :func:`named` takes it.

    Returns:
      Its path, or None where there is no build for that machine.
    """
    where = named(system, machine)
    if where is None:
        return None
    if where == named(platform.system(), platform.machine()):
        return found()
    if (path := packaged(system, machine)) is not None:
        return path
    crate = Path(__file__).resolve().parents[3] / "crates" / "coganchor" / "target"
    for profile in ("release", "debug"):
        if (path := crate / _TRIPLES[where] / profile / "coganchor").is_file():
            return path
    return None


def digest(path: Path) -> str:
    """What a build is named by on a target: the start of its SHA-256, in hex.

    Read once per version of the file in a process, a build being megabytes and the question
    being asked for every line that ships it.

    Args:
      path: The build.

    Returns:
      Its first 16 hex digits.

    Raises:
      OSError: If it cannot be read.
    """
    held = path.stat()
    key = (str(path), held.st_size, held.st_mtime_ns)
    if (known := _DIGESTS.get(key)) is not None:
        return known
    with path.open("rb") as reading:
        said = hashlib.file_digest(reading, "sha256").hexdigest()[:_DIGEST]
    _DIGESTS[key] = said
    return said


#: What each build read was found to be, by its path, size and modification time.
_DIGESTS: dict[tuple[str, int, int], str] = {}


def chosen() -> Path | None:
    """The `coganchor` `HUMANIZE_COGANCHOR` names, where it names a file.

    Returns:
      Its path, or None where the variable is unset, empty or names nothing.
    """
    said = os.environ.get(VARIABLE, "").strip()
    if not said:
        return None
    path = Path(said).expanduser()
    return path if path.is_file() else None


def translated(command: str, argv: list[str]) -> list[str]:
    """The `coganchor` line that does what `hmz internal <command> <argv>` does.

    Args:
      command: `anchor`, `fence` or `cred`.
      argv: What followed the command's name.

    Returns:
      The arguments to give `coganchor`, without its own name.

    Raises:
      ValueError: For a command `coganchor` does not carry out.
    """
    if command == "anchor":
        if argv[:1] == ["serve"]:
            return ["anchor", *argv[1:]]
        if argv[:1] == ["rendezvous"]:
            return ["broker", *argv[1:]]
        return ["cog", *argv]
    if command in ("fence", "cred"):
        return ["internal", command, *argv]
    raise ValueError(f"coganchor does not run `hmz internal {command}`")
