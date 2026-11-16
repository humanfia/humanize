"""The relay of `hmz relay serve`: where a daemon and a device that cannot dial it meet.

:mod:`hmz.relay.rooms` keeps a room for each daemon registered with it and joins clients to
them -- a byte splice for a native client, signals passed through for a browser -- and
:mod:`hmz.relay.proof` is the one check it makes of anybody: that a daemon holds the key its id
was made of. It reads nothing of this machine's, and carries nothing it can read.
"""

from __future__ import annotations

from .proof import CONTEXT, fingerprint, proven
from .rooms import (
    ANSWERING,
    BINARY,
    PINGING,
    SILENT,
    TEXT,
    Peer,
    Relay,
    listening,
)

__all__ = [
    "ANSWERING",
    "BINARY",
    "CONTEXT",
    "PINGING",
    "SILENT",
    "TEXT",
    "Peer",
    "Relay",
    "fingerprint",
    "listening",
    "proven",
]
