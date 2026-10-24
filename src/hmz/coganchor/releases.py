"""Which release of Humanize is the newest, as PyPI says, kept for this machine a day at a time.

What `hmz update` installs and what the interfaces say is out. Asked of PyPI's JSON API, whose
`info.version` is the newest release that is not a pre-release, and kept in Humanize's
directory for this machine, so that neither interface reaches for the network more than once
a day, nor waits on it at all: :func:`newer` reads what was kept, and :func:`refresh` is asked
for by whoever has a thread to spare.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import pathlib
import time
import urllib.error
import urllib.request
from typing import cast

from packaging.version import InvalidVersion, Version

from hmz import machine
from hmz.coganchor import atomic

__all__ = ["SOURCE", "STALE", "WHENCE", "fetch", "latest", "newer", "refresh", "where"]

#: What PyPI says of the package, the newest release among it.
SOURCE = "https://pypi.org/pypi/hmz/json"

#: What names another URL or file to read instead, and what turns the asking off altogether
#: -- which is what an air-gapped install wants, and what this suite is run under.
WHENCE = "HUMANIZE_RELEASES"

#: How old what is kept may get before it is asked again.
STALE = 24 * 60 * 60.0

#: How long PyPI is given to answer.
_WAITING = 10.0

#: The most that will be read of the answer, which lists every file of every release.
_MOST = 16 * 1024 * 1024


def where() -> pathlib.Path:
    """Where the newest release is kept, which is this machine's alone."""
    return machine() / "releases.json"


def latest() -> str | None:
    """The newest release kept here, or None where none ever was."""
    try:
        said: object = json.loads(where().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    found = (
        cast("dict[str, object]", said).get("latest")
        if isinstance(said, dict)
        else None
    )
    return found if isinstance(found, str) and found else None


def newer() -> str | None:
    """The newest release kept here where it is newer than the one running, or None.

    A source tree says `0.0.0`, as `pyproject.toml` does on `main`, and is behind no release.
    """
    from hmz.coganchor import __version__

    found = latest()
    if found is None or __version__ in {"0.0.0", "unknown"}:
        return None
    try:
        return found if Version(found) > Version(__version__) else None
    except InvalidVersion:
        return None


def refresh(*, wait: bool = False) -> None:
    """Asks again which release is the newest, where what is kept has got old.

    Args:
      wait: Whether to ask on this thread instead of on one of its own.
    """
    if not _whence() or _fresh():
        return
    if wait:
        fetch()
        return
    import threading

    threading.Thread(target=fetch, daemon=True, name="humanize-releases").start()


def fetch() -> str | None:
    """Asks which release is the newest now, however recently it was asked, and keeps it.

    Returns:
      It, or None where it could not be asked or did not answer with one -- or where asking
      has been turned off.
    """
    whence = _whence()
    if not whence:
        return None
    try:
        if "://" in whence:
            asked = urllib.request.Request(  # noqa: S310 -- the scheme is checked below
                whence, headers={"Accept": "application/json", "User-Agent": "humanize"}
            )
            if asked.type not in {"http", "https"}:
                return None
            with urllib.request.urlopen(asked, timeout=_WAITING) as answer:  # noqa: S310
                body = answer.read(_MOST)
        else:
            body = pathlib.Path(whence).read_bytes()
        found = json.loads(body)["info"]["version"]
        Version(found)
    except (
        OSError,
        http.client.HTTPException,
        urllib.error.URLError,
        ValueError,
        KeyError,
        TypeError,
        InvalidVersion,
    ):
        return None
    if not isinstance(found, str):
        return None
    with contextlib.suppress(OSError):
        kept = where()
        kept.parent.mkdir(parents=True, exist_ok=True)
        atomic.writes(kept, json.dumps({"latest": found}))
    return found


def _whence() -> str:
    """The source, which an environment variable may point elsewhere or turn off."""
    said = os.environ.get(WHENCE)
    if said is None:
        return SOURCE
    said = said.strip()
    return "" if said.lower() in {"", "off", "0", "no", "none"} else said


def _fresh() -> bool:
    """Whether what is kept is new enough that asking again would buy nothing."""
    try:
        return time.time() - where().stat().st_mtime < STALE
    except OSError:
        return False
