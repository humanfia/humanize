"""A workspace's runs, carried between the host holding them and this machine's daemon.

The runs themselves are :class:`hmz.runtime.Host`'s: the run going, who holds which role, what
is waiting to be said, what every frontend has been told. What is here is only the link to the
daemon and the process it is carried in, which a terminal closing cannot end. A host listens
for nobody: the daemon starts it with one end of a socket pair, and every frontend reaches it
through the daemon, which ends each client's session and speaks for its subscriptions down
that link. The link is JSON-RPC as every session is (`hmz.rpc`), of calls of its own which no
client ever sees:

- `attach` `{tag, name, kind, replay, since}`: takes a frontend on, answering its client id;
  every message it is told goes back as the notification `told` `{tag, message}`.
- `ask` `{client, said}`: what a frontend asked, answered as :meth:`hmz.runtime.Host.asked`
  answers it.
- `chat` `{said}`: what `chat.*` asks of the chat held, by nobody attached, answered as
  :meth:`hmz.runtime.Host.chatted` answers it.
- `detach` `{client}`: lets a frontend go.
- `env` `{said}`: a `hosts.env.*` on the epic going, which no frontend asks, answered as
  :meth:`hmz.runtime.Host.env` answers it.
- `status`: how the host stands, with what it said of itself.
- `detach_all`: lets every frontend go, answering how many.
- `close`, a notification: closes the host.

And one notification of the host's own, the last thing it says: `went`, how it stands as it
goes -- as `status` would have answered -- since nobody can ask it once it has gone, and an epic
that ended a moment before is still to be told of.

Nothing here waits on a frontend: the host keeps each one's messages and lets go of one too far
behind, and the daemon reads the link as fast as it is written.
"""

from __future__ import annotations

import contextlib
import io
import os
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where

if TYPE_CHECKING:
    import socket
    from collections.abc import Callable

    from hmz.rpc import Call, Peer
    from hmz.runtime import Host

__all__ = ["HOST_LOG", "Carrier", "Printed", "keeps", "logged", "serves"]

#: What a host process wrote while it held a run, in that run's epic: what the CLIs it
#: started wrote straight to a descriptor, and every line :func:`logged` wrote.
HOST_LOG = "host.log"

#: How much is read off a pipe at a time.
_READ = 1 << 16

#: How often the host looks at whether it is still wanted.
_TICK = 0.5

#: How long a host nobody has reached yet waits for somebody to: whoever asked for it is a
#: moment away from attaching, and one that never does must not leave a process behind.
_GRACE = 60.0


def logged(about: str) -> None:
    """Writes down what went wrong where nobody was reading a terminal to see it.

    On the process's own descriptor 2 rather than `sys.stderr`, which in a host is what is
    said to its frontends: in a host that descriptor is kept in the epic of the run it is
    holding (see :func:`keeps`), and in this machine's daemon, which holds no run, beside its
    socket.

    Args:
      about: What was being done, since whatever is being handled is what raised.
    """
    import sys

    handling = sys.exc_info()[0] is not None
    said = f"{about}\n{traceback.format_exc() if handling else ''}\n"
    with contextlib.suppress(OSError):
        os.write(2, said.encode(errors="replace"))


def _quietly(hook: Callable[[], object]) -> None:
    """Runs a hook that must not be able to end what is carrying the run."""
    with contextlib.suppress(Exception):
        hook()


class Carrier:
    """The host's end of its link to the daemon: what the daemon asks, carried out.

    Args:
      host: The runs being carried.
      said: What the host says of itself, which `status` is answered with as well.
    """

    def __init__(self, host: Host, said: dict[str, Any]) -> None:
        self._host = host
        self._own = said
        self.peer: Peer | None = None
        #: Whether a frontend has ever attached, after which an idle host goes at once.
        self.ever = False

    def serve(self, call: Call) -> None:
        """Takes one call or notification of the daemon's, carried out off the reading thread."""
        if call.method == "close":
            threading.Thread(
                target=_quietly, args=(self._host.close,), daemon=True
            ).start()
            return
        threading.Thread(
            target=self._carries, args=(call,), daemon=True, name="hmz-host-call"
        ).start()

    def _carries(self, call: Call) -> None:
        from hmz.rpc import RpcError

        try:
            call.answer(self._answers(call.method, call.params))
        except Exception as why:  # noqa: BLE001 -- a call that failed is answered as one
            call.fail(RpcError.unanticipated(why))

    def _answers(self, method: str, said: dict[str, Any]) -> Any:
        host = self._host
        if method == "attach":
            tag = str(said["tag"])
            since = said.get("since")
            client = host.attach(
                str(said.get("name") or ""),
                str(said.get("kind") or "sdk"),
                lambda message: self._told(tag, message),
                replay=said.get("replay", True) is not False,
                since=_since(since),
            )
            self.ever = True
            return {"client": client}
        if method == "ask":
            return host.asked(str(said["client"]), dict(said["said"]))
        if method == "chat":
            return host.chatted(dict(said["said"]))
        if method == "env":
            return host.env(dict(said["said"]))
        if method == "detach":
            host.detach(str(said["client"]))
            return {}
        if method == "status":
            return {**self._own, **host.status()}
        if method == "detach_all":
            clients = [one["client"] for one in host.status()["clients"]]
            for client in clients:
                host.detach(client)
            return {"let_go": len(clients)}
        raise ValueError(f"no such call as {method}")

    def _told(self, tag: str, message: dict[str, Any]) -> None:
        """Hands one message for one frontend down the link, on that frontend's thread."""
        from hmz.rpc import Closed

        if self.peer is not None:
            with contextlib.suppress(Closed):
                self.peer.notify("told", {"tag": tag, "message": message})


def _since(said: object) -> tuple[str, int] | None:
    """An `epic.attach`'s `since`, as the host takes it."""
    if not isinstance(said, dict):
        return None
    since = cast("dict[str, Any]", said)
    return str(since["epoch"]), int(since["seq"])


class Printed(io.TextIOBase):
    """What a host process prints, said to every frontend a line at a time.

    Put where `sys.stdout` and `sys.stderr` were in the process holding the runs: a flow
    prints, and so does a layer under one, and nobody is reading that process's terminal.
    """

    def __init__(self, host: Host) -> None:
        """Holds what to tell.

        Args:
          host: The runs whose frontends are told.
        """
        super().__init__()
        self._host = host
        self._held = ""
        self._lock = threading.Lock()

    #: What it is written in, which is what a library checking before it writes asks.
    encoding = "utf-8"

    def writable(self) -> bool:
        """It is written to."""
        return True

    def write(self, s: str) -> int:
        """Takes what was printed, and says each line that is whole.

        Args:
          s: What was printed.

        Returns:
          How much of it was taken, which is all of it.
        """
        with self._lock:
            *lines, self._held = (self._held + s).split("\n")
        for line in lines:
            self._host.printed(line)
        return len(s)


def keeps(reading: int, host: Host) -> None:
    """Writes what the process holding a workspace's runs writes into the run it belongs to.

    Everything a CLI a run starts writes straight to a descriptor, and every line
    :func:`logged` writes, arrives here down a pipe and goes into the epic of the run the host
    is holding, as :data:`HOST_LOG` beside its `epic.jsonl`: what went wrong in a run is read
    where the run is. What arrives before the host has held any run belongs to none, and goes
    beside this machine's daemon socket instead. Returns once nothing can write to the pipe.

    Args:
      reading: The pipe's end to read.
      host: The runs, asked for the epic of the one it is holding as each piece arrives.
    """
    while said := os.read(reading, _READ):
        with contextlib.suppress(OSError):
            epic = host.epic
            into = epic / HOST_LOG if epic is not None else where.at() / where.LOG
            writing = os.open(into, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(writing, said)
            finally:
                os.close(writing)


def serves(
    host: Host,
    workspace: str,
    link: socket.socket,
    telling: int | None = None,
    *,
    slot: str = "",
) -> None:
    """Holds a workspace's runs for this machine's daemon, over a link, until done.

    Goes once the host has closed: stopped, its daemon gone, or idle -- nothing running and
    nobody attached, once somebody has been or for a minute after it started.

    Args:
      host: The runs.
      workspace: The workspace they are held in, as :func:`hmz.daemon.where.workspace` says it.
      link: This end of the socket pair the daemon started it with.
      telling: A descriptor to say on that it is ready, and then close, or None.
      slot: Which of the workspace's hosts this is: "" for its own, `chat:<hex>` for a chat's,
        `exec:<hex>` for an `hmz exec`'s.
    """
    from hmz.reach.pipes import SocketPipe
    from hmz.rpc import PROTOCOL, Peer

    said: dict[str, Any] = {
        "pid": os.getpid(),
        "workspace": workspace,
        "slot": slot,
        "started": where.now(),
        "kind": "host",
        "protocol": PROTOCOL,
    }
    carrier = Carrier(host, said)
    peer = Peer(SocketPipe(link, trusted=True), carrier.serve, name="hmz-host-link")
    carrier.peer = peer
    if telling is not None:
        # Said and left open: the descriptor is whoever forked this one's to close.
        with contextlib.suppress(OSError):
            os.write(telling, b"listening\n")
    began = time.monotonic()
    try:
        while not host.closed:
            if peer.wait(_TICK):
                # The daemon has gone, and with it the only way anybody reaches these runs:
                # they are closed as a stop closes them, rather than left running for nobody.
                break
            if host.idle and (carrier.ever or time.monotonic() - began > _GRACE):
                host.close()
    finally:
        host.close()
        # How it stood as it goes, which nobody can ask of it after: the epic that just ended
        # here is still to be made a notice of (Section 4.19.1.1 of daemon.md).
        with contextlib.suppress(Exception):
            peer.notify("went", {**said, **host.status()})
        peer.close()
