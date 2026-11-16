"""Where `coganchor` is: the anchor, as one program built from `crates/coganchor`.

The anchor is being ported from this package to Rust, unit by unit, and until the port is
whole the Python halves still run by default. `HUMANIZE_COGANCHOR` naming a built binary
switches `hmz internal anchor`, `hmz internal fence` and `hmz internal cred` over to it, which
is how the port is tested against the suites that test the Python halves.

Once it is whole, the wheel carries a build for every platform a target can be, under
`bin/<os>-<arch>/coganchor` beside this module, and :func:`found` is what reaches it.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

__all__ = ["VARIABLE", "chosen", "found", "named", "packaged", "translated"]

#: The variable naming a built `coganchor` to run instead of the Python halves.
VARIABLE = "HUMANIZE_COGANCHOR"

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
