"""The daemon ids a client of this machine pins, as `settings.toml` keeps them under `daemons`.

A client knows another machine's daemon by its id alone, and learns it once: from a pairing
code, or from what the daemon said over a carrier that already proved who it is. Every later
session is held to it. Keeping the list -- adding, renaming, removing a daemon -- is the
registry's; this reads what it kept.
"""

from __future__ import annotations

import re
import secrets
from typing import Any, cast

from hmz.trust.identity import is_fingerprint

__all__ = ["matches", "pinned"]

#: What a remote daemon's name is: a letter or a digit, then letters, digits, `.`, `_`, `-`.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: The keys an entry of `daemons` has, and no others.
_KEYS = frozenset({"name", "id", "routes"})


def pinned(name: str) -> str | None:
    """The daemon id the client pins for a daemon of another machine.

    Args:
      name: What the client calls it.

    Returns:
      The id; `""` where it was never reached over a trusted carrier nor paired by a code,
      which pins nothing yet -- an entry an earlier release wrote included; and None where
      `daemons` has no entry of that name that can be read.
    """
    from hmz.coganchor import settings

    held: object = settings.read().get("daemons")
    if not isinstance(held, list):
        return None
    seen: set[str] = set()
    for one in cast("list[object]", held):
        if not isinstance(one, dict):
            continue
        entry = cast("dict[str, Any]", one)
        called = entry.get("name")
        if not isinstance(called, str) or called in seen:
            continue
        if "via" in entry:
            seen.add(called)
            if called == name:
                return ""
            continue
        if (
            frozenset(entry) != _KEYS
            or not _named(called)
            or not _routed(entry["routes"])
        ):
            continue
        said = entry["id"]
        if said != "" and not is_fingerprint(said):
            continue
        seen.add(called)
        if called == name:
            return cast("str", said)
    return None


def matches(fingerprint: str, pin: str) -> bool:
    """Whether a daemon's key is the one pinned: never, where nothing is pinned yet.

    Args:
      fingerprint: The SPKI fingerprint of the certificate the daemon presented.
      pin: The daemon id the client pins.
    """
    return bool(pin) and secrets.compare_digest(fingerprint.encode(), pin.encode())


def _named(name: str) -> bool:
    """Whether a name can be a remote daemon's: of the grammar, and not `local` in any case."""
    return _NAME.fullmatch(name) is not None and name.lower() != "local"


def _routed(routes: object) -> bool:
    """Whether what an entry gives as routes is a non-empty list of text."""
    if not isinstance(routes, list):
        return False
    listed = cast("list[object]", routes)
    return bool(listed) and all(isinstance(one, str) for one in listed)
