"""`session.hello`, the first call of every session, and which protocol versions it admits.

A client says its protocol version and who it is (Section 6.5.3 of wire.md); the daemon admits
a client of its own major version and a minor version no greater than its own, and refuses
every other with 426, its `data` holding the daemon's own version and its message saying which
of the two is the older (Section 6.5.5 and Section 6.5.6).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

from semver import Version

from hmz.rpc.errors import Code, RpcError

if TYPE_CHECKING:
    from hmz.rpc.peer import Peer

__all__ = ["PROTOCOL", "admit", "hello"]

#: The protocol version this implementation speaks (Section 6.5.1).
PROTOCOL = "3.0.0"

#: What a client is, among those Section 6.5.3 names.
type Kind = Literal["tui", "web", "desktop", "cli", "sdk", "bridge", "ai-chan"]


def hello(
    peer: Peer,
    name: str,
    kind: Kind,
    *,
    protocol: str = PROTOCOL,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Opens a session from the client's end: the call it makes first.

    Args:
      peer: The client's end of the session.
      name: The user's name for the client.
      kind: What the client is.
      protocol: The protocol version it says it speaks.
      timeout: How many seconds to wait for the answer, or `None` for as long as it takes.

    Returns:
      What the daemon answered: its id, its versions, whether the session is paired, and the
      rest of Section 6.5.4.

    Raises:
      RpcError: 426 where the daemon speaks another protocol, after which nothing more may be
        called on the session and the error's message is what to report (Section 6.5.7).
      Closed: If the session closed first.
      TimeoutError: If `timeout` passed first.
    """
    client = {"name": name, "kind": kind}
    return peer.call(
        "session.hello", {"protocol": protocol, "client": client}, timeout=timeout
    )


def admit(theirs: str, *, ours: str = PROTOCOL, pid: int | None = None) -> None:
    """Checks a client's protocol version from the daemon's end, as `session.hello` gives it.

    Args:
      theirs: The protocol version the client said.
      ours: The daemon's.
      pid: The daemon's process id, which the refusal of a newer client names; this process's
        where none is given.

    Raises:
      RpcError: 426 where the client speaks a protocol the daemon does not admit, and -32602
        where what it said is not a version at all.
    """
    try:
        client = Version.parse(theirs)
    except ValueError:
        raise RpcError(
            Code.INVALID_PARAMS, "session.hello takes protocol as a version."
        ) from None
    own = Version.parse(ours)
    if client.major == own.major and client.minor <= own.minor:
        return
    if client < own:
        message = "held for frontends by a newer Humanize; `hmz` of it reads it"
    else:
        held = os.getpid() if pid is None else pid
        message = (
            f"the runs on this machine are held by an older Humanize (pid {held}); "
            "stop it with that version"
        )
    raise RpcError(Code.PROTOCOL_MISMATCH, message, {"protocol": ours})
