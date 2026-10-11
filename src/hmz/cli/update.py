"""``hmz update`` -- this install of humanize, moved to its newest release.

Moved by whatever installed it, rather than by a copy of what that tool does: `uv tool
upgrade` for a uv tool, `pipx upgrade` for a pipx one -- each keeping the extras it was
installed with -- and pip, or uv's pip, for an environment somebody made, asked for the
extras whose packages are there. An install from a checkout or a URL is that source's to
move, and is said to be. What is running keeps running the release it started under: the
daemon holding this machine's epics included, which is said where there is one.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

__all__ = ["update"]

#: What `uv tool` and pipx each leave in an environment they made.
_UV_TOOL = "uv-receipt.toml"
_PIPX = "pipx_metadata.json"


def update(argv: list[str]) -> int:
    """Updates hmz to its newest release, however it was installed.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once it is the newest release; one where it could not be made so.
    """
    import argparse

    argparse.ArgumentParser(
        prog="hmz update",
        description="Update hmz to its newest release, with whatever installed it.",
    ).parse_args(argv)

    from packaging.version import Version

    from hmz.coganchor import __version__, releases

    how = _how()
    if isinstance(how, str):
        print(f"hmz update: {how}", file=sys.stderr)
        return 1
    newest = releases.fetch()
    if newest is None:
        print(
            "hmz update: PyPI could not be asked for the newest release",
            file=sys.stderr,
        )
        return 1
    if Version(newest) <= Version(__version__):
        print(f"hmz {__version__} is the newest release")
        return 0
    # Flushed: what the installer writes next goes to the same terminal, on its own.
    print(f"Updating hmz {__version__} to {newest}: {' '.join(how)}", flush=True)
    done = subprocess.run(how, check=False)
    if done.returncode:
        print(f"hmz update: {how[0]} exited {done.returncode}", file=sys.stderr)
        return 1
    now = _installed()
    if now != newest:
        print(
            f"hmz update: {how[0]} left hmz at {now or 'an unknown version'}, "
            f"not {newest}",
            file=sys.stderr,
        )
        return 1
    print(f"Updated hmz to {newest}")
    from hmz import daemon

    if held := daemon.daemons():
        print(
            f"Epics held on this machine (pid {held[0].pid}) run hmz {__version__} "
            "until that daemon stops"
        )
    return 0


def _how() -> list[str] | str:
    """The line that moves this install to the newest release, or why there is none."""
    try:
        installed = distribution("hmz")
    except PackageNotFoundError:
        return "hmz is not installed here, only run from its source"
    source = installed.read_text("direct_url.json")
    if source:
        import json

        url = json.loads(source).get("url", "")
        return f"hmz was installed from {url}, not PyPI; update it there"
    prefix = Path(sys.prefix)
    if (prefix / _UV_TOOL).is_file():
        return _found("uv", "tool", "upgrade", "hmz")
    if (prefix / _PIPX).is_file():
        return _found("pipx", "upgrade", "hmz")
    extras = _extras()
    wanted = f"hmz[{','.join(extras)}]" if extras else "hmz"
    import importlib.util

    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install", "--upgrade", wanted]
    return _found(
        "uv", "pip", "install", "--python", sys.executable, "--upgrade", wanted
    )


def _found(program: str, *args: str) -> list[str] | str:
    """A line running a program on `PATH`, or why it cannot be run."""
    at = shutil.which(program)
    if at is None:
        return f"{program} installed hmz but is not on PATH"
    return [at, *args]


def _extras() -> list[str]:
    """The extras whose packages are all installed, but those naming only hmz's own others.

    pip writes down no extras, so they are read off what is there: `all` is `hmz[...]` of
    the others, and is taken by taking them.
    """
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    installed = distribution("hmz")
    needs = [Requirement(one) for one in installed.requires or []]
    found: list[str] = []
    for extra in installed.metadata.get_all("Provides-Extra") or []:
        theirs = [
            one
            for one in needs
            if one.marker is not None
            and one.marker.evaluate({"extra": extra})
            and not one.marker.evaluate({"extra": ""})
            and canonicalize_name(one.name) != "hmz"
        ]
        if theirs and all(_there(one.name) for one in theirs):
            found.append(extra)
    return found


def _there(name: str) -> bool:
    """Whether a distribution is installed beside this one."""
    try:
        distribution(name)
    except PackageNotFoundError:
        return False
    return True


def _installed() -> str:
    """The version of hmz installed now, asked of a fresh interpreter, or "" where none says."""
    said = subprocess.run(
        [
            sys.executable,
            "-c",
            "from importlib.metadata import version; print(version('hmz'))",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return said.stdout.strip() if said.returncode == 0 else ""
