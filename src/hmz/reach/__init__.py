"""Reaching a daemon: the carriers between a client and a daemon, and the routes that name them.

The lowest layer of the wire protocol, L0: any ordered, reliable stream of bytes each way
(Section 3 of `protocol/wire.md`). A route is the text that names one; :func:`dial` opens it
from a client's side and :class:`TcpListener` and :class:`RelayListener` accept one on a
daemon's; and what each gives is a :class:`hmz.rpc.Pipe`, trusted where the operating system,
`ssh` or WSL already admitted the client as the daemon's user, and untrusted otherwise. What
goes over a pipe -- mutual TLS on an untrusted one, then the frames -- is `hmz.trust`'s and
`hmz.rpc`'s.

:func:`race` tries the routes of one daemon in turn and keeps the first to get through a
handshake; :class:`Backoff` spaces the tries of one lost. :func:`splice` is `hmz daemon
connect --stdio`, its standard streams joined to the daemon's socket once it has written
:data:`SYNC`, which a `stdio:` carrier begins after.
"""

from __future__ import annotations

from hmz.reach.dialing import OPENING, EasyTier, command, dial, websocket
from hmz.reach.listening import TcpListener
from hmz.reach.pipes import (
    MESSAGE,
    SYNC,
    Messages,
    ProcessPipe,
    SocketPipe,
    StreamPipe,
    WebSocketPipe,
    splice,
    stdio,
)
from hmz.reach.racing import FIRST, LONGEST, STAGGER, Backoff, Won, race
from hmz.reach.relays import RelayListener, join
from hmz.reach.routes import KINDS, TRUSTED, Route

__all__ = [
    "FIRST",
    "KINDS",
    "LONGEST",
    "MESSAGE",
    "OPENING",
    "STAGGER",
    "SYNC",
    "TRUSTED",
    "Backoff",
    "EasyTier",
    "Messages",
    "ProcessPipe",
    "RelayListener",
    "Route",
    "SocketPipe",
    "StreamPipe",
    "TcpListener",
    "WebSocketPipe",
    "Won",
    "command",
    "dial",
    "join",
    "race",
    "splice",
    "stdio",
    "websocket",
]
