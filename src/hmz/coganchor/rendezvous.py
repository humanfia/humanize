"""Where two halves of a session meet when neither can dial the other.

An anchor reaches a target by starting the serving half itself -- over `ssh`, over `docker
exec`, as a child here -- and the channel is the pipe it started it down. That answer runs out
the moment the two halves are on two *different* machines that Humanize only talks to one at a
time: the agent runs on one, its work lands on the other, and nothing either of them has says
how to reach the other one. Both can reach Humanize, which is the whole of what this is built
on.

So Humanize holds the meeting. A ticket names it -- one secret, one session -- and each half
dials a broker with it and says which half it is. The broker tells each half what the other
looks like from outside, starts them at each other at the same instant so that a hole is
punched through whatever NAT is between them, and carries the bytes itself when none can be.

The broker and both halves' dialling are `coganchor`'s (`coganchor broker`, `coganchor anchor
--peer`, and `coganchor cog` for a `peer://` target). What is left here is what this process
needs to book one: a ticket, the :class:`Meeting` it names, and the one broker this process
holds, started as `coganchor broker` the first time it is asked for (:func:`shared`).
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import os
import queue
import secrets
import socket
import subprocess
import threading
import time
from dataclasses import dataclass

__all__ = ["Meeting", "shared", "ticket"]

log = logging.getLogger(__name__)

#: What a broker says on its stderr once it listens, before the host and the port it landed on.
_LISTENING = "hmz internal anchor rendezvous listening "

#: How long a broker started here has to say it listens before it is taken for one that won't.
_STARTING = 30.0


def ticket() -> str:
    """Mints a name for one meeting, which is also the secret that gets into it.

    Returns:
      A fresh ticket. Long enough that the only way to hold one is to have been told it,
      which is what stands in for every other kind of authentication here.
    """
    return secrets.token_hex(16)


@dataclass(frozen=True, slots=True)
class Meeting:
    """One session's meeting: which broker holds it, and under what name.

    Attributes:
      ticket: The secret naming the meeting. Both halves present it; nothing else is asked
        of either, so a ticket is the whole of what may not be shared.
      host: Where the broker is, as both halves can reach it.
      port: The port it is listening on.
    """

    ticket: str
    host: str
    port: int

    @classmethod
    def parse(cls, spec: str) -> Meeting:
        """Reads a meeting out of its `TICKET@HOST:PORT` spelling.

        Args:
          spec: The spelling, as a `peer://` target carries it.

        Returns:
          The meeting it names.

        Raises:
          ValueError: If it is not one.
        """
        name, at, authority = spec.partition("@")
        host, colon, port = authority.rpartition(":")
        if not (name and at and host and colon and port.isdigit()):
            raise ValueError(f"malformed meeting {spec!r}; expected TICKET@HOST:PORT")
        return cls(name, host.strip("[]"), int(port))

    def __str__(self) -> str:
        return f"{self.ticket}@{self.host}:{self.port}"


#: The broker this process runs, as the `coganchor broker` holding it and the port it landed
#: on, started when something first needs it and kept afterwards: a run that anchors a hundred
#: turns across a dozen machines pays for one of them.
_here: tuple[subprocess.Popen[bytes], int] | None = None
_SHARING = threading.Lock()


def shared(advertise: str = "") -> tuple[str, int]:
    """The broker this process holds, started on first use and kept for the rest of the run.

    `coganchor broker`, listening on every interface at the port `HUMANIZE_RENDEZVOUS_PORT`
    names, else any free one -- which it says on its stderr, where it is read off. Started
    again where the one started before has gone, and ended as this process exits.

    Args:
      advertise: The address the two halves should dial, for a machine whose own name is not
        the one they can reach it by. Empty asks this machine which of its addresses faces
        outward, which is right wherever the halves are on the same network as this one.

    Returns:
      The host and port to hand the halves.

    Raises:
      OSError: If there is no `coganchor` for this machine, or it cannot listen.
      ValueError: If `HUMANIZE_RENDEZVOUS_PORT` is not a number.
    """
    global _here  # noqa: PLW0603 -- one per process is the point
    with _SHARING:
        if _here is None or _here[0].poll() is not None:
            _here = _started(int(os.environ.get("HUMANIZE_RENDEZVOUS_PORT", "0")))
        _, port = _here
        return advertise or os.environ.get("HUMANIZE_RENDEZVOUS") or _facing(), port


def _started(port: int) -> tuple[subprocess.Popen[bytes], int]:
    """Starts `coganchor broker` on a port, and reads which one it landed on.

    Raises:
      OSError: If there is no `coganchor` for this machine, or it did not say it listened --
        having ended first, said something else, or said nothing for :data:`_STARTING`
        seconds -- when it is ended, if it has not.
    """
    from hmz.coganchor import binary

    try:
        program = binary.here()
    except FileNotFoundError as missing:
        raise OSError(str(missing)) from missing
    started = subprocess.Popen(
        [str(program), "broker", "--listen", f"0.0.0.0:{port}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    heard: queue.Queue[str | None] = queue.Queue()
    threading.Thread(
        target=_said, args=(started, heard), name="rendezvous", daemon=True
    ).start()
    said: list[str] = []
    until = time.monotonic() + _STARTING
    try:
        while (left := until - time.monotonic()) > 0:
            try:
                line = heard.get(timeout=left)
            except queue.Empty:
                break
            if line is None:
                break
            if line.startswith(_LISTENING):
                landed = int(line.split()[-1])
                atexit.register(_ended, started)
                return started, landed
            said.append(line)
    except ValueError:
        pass
    _ended(started)
    raise OSError(
        f"the rendezvous broker did not say it listened: {' '.join(said)[-400:]}"
    )


def _said(started: subprocess.Popen[bytes], heard: queue.Queue[str | None]) -> None:
    """Hands on what a broker says until it listens, and logs it after, until it is done.

    Read for as long as it says anything, so a broker with a lot to say never stops on a pipe
    nobody empties; `None` once it has said everything it will.
    """
    assert started.stderr is not None  # noqa: S101
    listening = False
    for raw in started.stderr:
        line = raw.decode(errors="replace").rstrip()
        if listening:
            log.debug("%s", line)
            continue
        heard.put(line)
        listening = line.startswith(_LISTENING)
    heard.put(None)


def _ended(started: subprocess.Popen[bytes]) -> None:
    """Ends a broker this process started, and reaps it."""
    if started.poll() is None:
        started.terminate()
        try:
            started.wait(timeout=5)
        except subprocess.TimeoutExpired:
            started.kill()
            started.wait()


def _facing() -> str:
    """Which of this machine's addresses another machine would reach it at.

    Asked of the routing table rather than of DNS: a hostname here may be one nothing else
    resolves, while the address the kernel would send from is the one a machine on the same
    network already has a route back to. Nothing is sent -- a connectionless socket only
    records where it would go.
    """
    with (
        contextlib.suppress(OSError),
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as asking,
    ):
        asking.connect(("192.0.2.1", 9))  # reserved for documentation; never routed
        return str(asking.getsockname()[0])
    return "127.0.0.1"
