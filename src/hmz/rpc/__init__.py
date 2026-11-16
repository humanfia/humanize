"""Frames and JSON-RPC 2.0 over any pipe: layers L2 and L3 of protocol/wire.md.

A session is a :class:`Pipe` -- a carrier, or the mutual TLS over one -- carrying frames, each
one JSON object behind its length (:mod:`hmz.rpc.frames`), each frame one JSON-RPC 2.0 call,
notification or response between two :class:`Peer` ends. One end serves methods through a
:class:`Dispatcher`, which serves only those the OpenRPC document (:func:`document`) lists, and
every session opens with `session.hello` (:func:`hello` and :func:`admit`).

Everything here is threads and blocking calls, as the daemon is: see :mod:`hmz.rpc.pipe` for why.
"""

from hmz.rpc.dispatch import Dispatcher, Handler
from hmz.rpc.document import document
from hmz.rpc.errors import Closed, Code, RpcError
from hmz.rpc.frames import LONGEST, FrameError, Frames, encode
from hmz.rpc.hello import PROTOCOL, Kind, admit, hello
from hmz.rpc.peer import Call, Peer, Pending
from hmz.rpc.pipe import Pipe

__all__ = [
    "LONGEST",
    "PROTOCOL",
    "Call",
    "Closed",
    "Code",
    "Dispatcher",
    "FrameError",
    "Frames",
    "Handler",
    "Kind",
    "Peer",
    "Pending",
    "Pipe",
    "RpcError",
    "admit",
    "document",
    "encode",
    "hello",
]
