"""Where two halves of a session meet when neither can dial the other.

An anchor reaches a target by starting the serving half itself -- over `ssh`, over `docker
exec`, as a child here -- and the channel is the pipe it started it down. That answer runs out
the moment the two halves are on two *different* machines that humanize only talks to one at a
time: the agent runs on one, its work lands on the other, and nothing either of them has says
how to reach the other one. Both can reach humanize, which is the whole of what this is built
on.

So humanize holds the meeting. A ticket names it -- one secret, one session -- and each half
dials this broker with it and says which half it is. Three things follow, in the order they
are tried, and a session takes the first that works:

**It says what each half looks like from outside.** The address a connection arrives from is
the address the world has for whoever opened it, which is the one thing a machine behind a NAT
cannot learn by asking itself. Each half is told its own, and each is given the other's
alongside the addresses that half knows for itself. That is the whole of what a STUN server
does, and it is one line of JSON here because it is one attribute of an accepted socket.

**It starts them at each other at the same instant.** Both halves open outward from the port
they dialled here from, and both listen on it, and they do it at once. Where a NAT is
address-independent -- which the common ones are -- each side's outbound attempt opens the
hole its peer's attempt arrives through, and the two meet in the middle with humanize no
longer in the path. A session that gets this far pays nothing per byte for having been
introduced.

**And it carries the bytes itself when they cannot.** Two symmetric NATs, a firewall that
drops what it did not see leave, a network that simply has no route: the punching window
closes, both halves say so, and the connections they are already holding *to this broker* are
spliced together. No second dial, no second port, no third machine -- the fallback costs one
message, because the relay is the socket the introduction was made over.

A ticket may be met at again, which is what a serving half nothing can start is for: one left
standing goes back to the meeting each time it is met, and every session is a meeting of its
own. A meeting stops taking halves once it has both, and a half arriving where one of its own
kind is already waiting waits behind it -- so two halves met under a ticket are never joined
by a third, and two arriving at once are each met in turn.

Such a meeting is booked with the broker rather than merely named (:meth:`Broker.stand`), and
has a ticket for each half. The serving half's is handed to a machine where anything that
runs may read it, so it lets in a serving half alone, and only the one that came with it
first -- by a key that half chose and never wrote down; the anchoring halves are given the
other. Holding the ticket a task was handed is then neither being that task nor reaching it.

Which of the three a session got is not a thing the session is told. The channel is a socket
either way, the protocol above it is the same protocol, and a flow that would have to behave
differently for a relayed session is a flow that would have to know something no end of a
connection can honestly report.

The whole of it is IPv4 and deliberately so: a hole is punched from one port to one address,
and a candidate the other half cannot open a matching socket for is a candidate that only
spends the window. A machine reachable only over IPv6 relays, which is the answer this already
has for every other unreachable pair.

**And a meeting may be sealed.** One that names a certificate (`?tls=DIR`) is held over TLS
1.3 end to end: every connection to the broker, and every punched one, before a word of this
protocol is said on it. Nothing is asked of an authority or of a name -- the certificate is
made for one broker of one run and handed to each half by whoever started it, so the one
question worth asking of a peer is whether it presented *exactly that one*, which nothing
without its key can do. The broker holds the key, and so does every anchoring half, which is
on the broker's machine: on a punched socket the anchoring half is the TLS server whichever
end dialled, and the serving half -- on a machine where anything that runs may read what it
was handed -- is only ever a client that checks. Tickets and keys are said inside it as
before, so holding the certificate is no more a way in than holding the ticket was.
"""

from __future__ import annotations

import contextlib
import errno
import functools
import hashlib
import hmac
import json
import logging
import os
import queue
import secrets
import select
import socket
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qsl, quote

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "ANCHOR",
    "CERTIFICATE",
    "SERVE",
    "Broker",
    "Meeting",
    "dial",
    "meet",
    "shared",
    "standing",
    "ticket",
]

log = logging.getLogger(__name__)

#: The half that runs the agent and asks the questions.
ANCHOR = "anchor"

#: The half that answers them, on the machine the work lands on.
SERVE = "serve"

#: Both of them, for reading a role off the wire without trusting what it says.
ROLES = frozenset({ANCHOR, SERVE})

#: What the other half is, for a half that has just said what it is.
_OPPOSITE = {ANCHOR: SERVE, SERVE: ANCHOR}

#: How long a half waits at the broker for the other one to arrive. Generous: the two are
#: started one after the other over links that may each take seconds to open, and a session
#: refused for being early is a session that would have worked a moment later.
PAIRING = 120.0

#: How long the two spend opening holes at each other before giving up and being carried.
#: Short, because a punch that is going to work works in the first round trip or two, and
#: every second past that is a second the session has not started in.
PUNCHING = 4.0

#: How long one punched socket has to prove it is the other half of this session. Shorter
#: still: both ends greet the instant the connection is up, so anything slower than this is a
#: connection to something that is not listening for us.
GREETING = 3.0

#: How long a half waits for its own machine's name to resolve before going without it.
_NAMING = 1.0

#: How long a half waits on the broker's own answers, which are sent as soon as it has them.
_ANSWERING = 30.0

#: How deep the queue of halves waiting to be accepted is allowed to get. `SOMAXCONN` is what
#: the kernel is willing to hold, and what is wanted here is all of it: the alternative to
#: queueing a connection is dropping it.
_BACKLOG = socket.SOMAXCONN

#: How many goes at taking one port for the two sockets that need it. A handful: each failure
#: is another socket's to have taken the port in between, which is a thing that happens and
#: not a thing that keeps happening.
_TRIES = 8

#: How many tickets one broker will hold at once. A backstop rather than a budget: a meeting
#: only exists while a half is connected to it, and a half is a connection and a thread, so
#: what actually bounds this is the same thing that bounds every other server. The number is
#: therefore set well past where those run out -- a hub introducing four thousand pairs at
#: once was refusing them here, at a cap chosen for the size of a dictionary rather than for
#: the size of a fleet, and the sessions it refused were sessions that would have worked.
_TICKETS = 1 << 16

#: How many meetings one ticket may have waiting at once. A ticket met at again has one
#: serving half, which goes back the moment it is met, so what waits is the sessions arriving
#: in that moment: a handful. Past this many is not a burst but something knocking.
_QUEUED = 64

#: How many halves one address may have connected to a broker of booked meetings before
#: saying which meeting they are for. The halves this machine itself sends are not counted --
#: a run starting its agents all at once is one address -- and nor is a half once it is let
#: in, so this costs nobody with a ticket anything, and anybody without one most of a thread.
_KNOCKING = 64

#: The most directories an anchoring half may ask its serving half for, and how long a name.
_ASKS = 64
_ASKED = 4096

#: How many pairs of machines a broker remembers having failed to introduce, and how often it
#: tries them again anyway. Two machines with no route between them do not grow one between
#: one session and the next, so a deployment that relays spends the whole punching window per
#: session for an answer it already has -- which at a hundred sessions is several minutes of
#: nothing happening. So the answer is kept, and every so often disbelieved: a firewall rule
#: *is* the kind of thing that changes, and a broker certain of an old one would keep carrying
#: sessions that could now go straight across.
_HOPELESS = 1024
_DISBELIEVING = 16

#: And how many failures it takes before the answer is believed at all. More than one, and
#: that matters: a pair here is named by the two addresses the world has for the two halves,
#: and every machine behind one NAT wears the same one. A single unlucky punch -- a port that
#: was not free for the moment it was wanted, a window that closed a beat early -- would
#: otherwise condemn every pair of machines behind those two addresses to being carried.
#: Something genuinely unroutable fails every time and reaches this in short order.
_CONVINCED = 3

#: What goes across a punched socket before anything else, so that neither half mistakes a
#: port scan, a health check or its own listener for the session it is waiting for. The digest
#: rather than the ticket: it proves the same knowledge and leaves the secret unsaid.
_MAGIC = b"HMZ1"

#: What the anchoring half says on the socket it has chosen, and what the serving half says
#: back on the one it accepts. Exactly one socket carries the pair, whichever of them won the
#: race, and every other one is closed by having heard neither.
_GO = b"GO"
_OK = b"OK"

#: The most a line of this protocol may be, so a peer that is not one cannot be read forever.
_LINE = 1 << 16

#: How much is moved at a time when the broker is carrying the session itself.
_RELAY = 1 << 16

#: What a sealed meeting's directory holds: the certificate every half pins, and -- on the
#: broker's machine alone -- the key it was made with.
CERTIFICATE = "cert.pem"
_KEY = "key.pem"


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
      tls: For a sealed meeting, the directory holding the certificate it is pinned to
        (:data:`CERTIFICATE`) -- and, for a half on the broker's machine, the key beside it;
        "" for a meeting held in the clear.
    """

    ticket: str
    host: str
    port: int
    tls: str = ""

    @classmethod
    def parse(cls, spec: str) -> Meeting:
        """Reads a meeting out of its `TICKET@HOST:PORT[?tls=DIR]` spelling.

        Args:
          spec: The spelling, as a `peer://` target carries it.

        Returns:
          The meeting it names.

        Raises:
          ValueError: If it is not one.
        """
        name, at, rest = spec.partition("@")
        authority, mark, query = rest.partition("?")
        host, colon, port = authority.rpartition(":")
        try:
            said = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            said = []
        # One thing may be said after a `?`, once, and it is a directory.
        tls = said[0][1] if len(said) == 1 and said[0][0] == "tls" else ""
        if not (name and at and host and colon and port.isdigit()) or (
            mark and not tls
        ):
            raise ValueError(
                f"malformed meeting {spec!r}; expected TICKET@HOST:PORT[?tls=DIR]"
            )
        return cls(name, host.strip("[]"), int(port), tls)

    def __str__(self) -> str:
        said = f"{self.ticket}@{self.host}:{self.port}"
        return f"{said}?tls={quote(self.tls, safe='/')}" if self.tls else said


def dial(
    meeting: Meeting,
    role: str,
    *,
    timeout: float = PAIRING,
    asks: Sequence[str] = (),
) -> socket.socket:
    """Meets the other half of a session and answers with the socket joining the two.

    The same call on both machines, differing only in which half is calling it. It returns
    when there is a connection the other half is holding the other end of -- punched through
    to that machine where the two could be introduced, carried by the broker where they could
    not -- and what it returns is a socket either way.

    Args:
      meeting: Which broker, and under what ticket.
      role: :data:`ANCHOR` or :data:`SERVE`, whichever half this is.
      timeout: How long to wait at the broker for the other half to arrive.
      asks: For an anchoring half, the directories it asks to be served, as `VIRTUAL[:REAL]`
        -- the `--export`s a serving half it started would have been started with. A
        serving half left standing serves each session only those (see :func:`meet`).

    Returns:
      The socket carrying the session. Blocking, with no timeout set, ready for
      :meth:`~hmz.coganchor.proto.Channel.from_socket`.

    Raises:
      ValueError: If `role` is not one of the two, or a sealed meeting's certificate is not
        one.
      OSError: If the broker cannot be reached -- or, at a sealed meeting, is not the one its
        certificate pins -- the other half never arrives, or the two could be neither
        introduced nor carried.
    """
    return meet(meeting, role, timeout=timeout, asks=asks)[0]


def meet(
    meeting: Meeting,
    role: str,
    *,
    timeout: float = PAIRING,
    key: str = "",
    asks: Sequence[str] = (),
) -> tuple[socket.socket, tuple[str, ...]]:
    """:func:`dial`, answering besides with what the other half asked of this one.

    What a serving half left standing at a booked meeting dials with: it proves with `key`
    that it is the half that first came with its ticket, and is told what each anchoring half
    met there asked to be served.

    Args:
      meeting: Which broker, and under what ticket.
      role: :data:`ANCHOR` or :data:`SERVE`, whichever half this is.
      timeout: How long to wait at the broker for the other half to arrive.
      key: For a serving half at a booked meeting, the secret it chose, the same every time.
      asks: For an anchoring half, the directories it asks to be served, as :func:`dial`.

    Returns:
      The socket carrying the session, as :func:`dial` answers it, and the directories the
      anchoring half asked for -- empty where it asked for none, and for an anchoring half.

    Raises:
      ValueError: If `role` is not one of the two, or a sealed meeting's certificate is not
        one.
      OSError: If a sealed meeting's certificate cannot be read, the broker cannot be
        reached, is not the one that certificate pins, or will not let this half in, the
        other half never arrives, or the two could be neither introduced nor carried.
    """
    if role not in ROLES:
        raise ValueError(f"unsupported role {role!r}; expected {ANCHOR} or {SERVE}")
    sealing = _sealing(meeting.tls) if meeting.tls else None
    # One port for both, taken before either is used for anything: the broker has to see this
    # half at the port its peer will be sent at, and the peer has to find something listening
    # there. Which of the two is opened first matters, and it is the listener -- see `_both`.
    home, ear, port = _both()
    punched: socket.socket | None = None
    try:
        home.settimeout(timeout)
        home.connect((meeting.host, meeting.port))
        at = _mine(home, port)
        if sealing is not None:
            home = sealing.sealed(home, server=False, timeout=_ANSWERING)
        lines = _Lines(home)
        hello: dict[str, Any] = {"ticket": meeting.ticket, "role": role, "at": at}
        if key:
            hello["key"] = key
        if asks:
            hello["export"] = list(asks)
        _say(home, hello)
        first = lines.read(timeout)
        if "seen" not in first:
            # Turned away at the door: the broker says why, and that is the answer.
            raise ConnectionError(  # noqa: TRY301 -- for the reason the ones below are
                str(first.get("why") or "the broker would not let this half in")
            )
        log.debug("the broker sees this half at %s", first["seen"])
        # A little longer than the broker is patient for, deliberately: the two are given the
        # same number, and a half that gave up on the same tick would answer with a bare
        # timeout instead of the broker's own account of what it had been waiting for.
        said = lines.read(timeout + _ANSWERING)
        if "peer" not in said:
            # Raised here rather than out of a helper: the `except` below is a cleanup of the
            # three sockets this call may be holding, not a handler, and moving the two ways
            # a meeting fails away from where they are noticed would say less.
            raise ConnectionError(  # noqa: TRY301
                str(said.get("why") or "the other half never arrived")
            )
        asked = _asked(said.get("export")) if role == SERVE else ()
        if asked is None:
            raise ConnectionError(  # noqa: TRY301 -- for the reason the one above is
                "the broker passed on something that is not a list of directories"
            )
        # What the two prove to each other on a punched socket: the ticket, unless the broker
        # says otherwise -- which it does for a booked meeting, whose halves hold two.
        proof = str(said.get("proof") or meeting.ticket)
        # A sealed anchoring half without the key cannot be the server of a punched socket,
        # and is carried instead: the one thing it cannot be is joined in the clear.
        if sealing is None or role == SERVE or sealing.server is not None:
            punched = _punch(
                ear,
                port,
                said["peer"],
                proof,
                role,
                float(said.get("punch", 0.0)),
                sealing,
            )
        _say(home, {"direct": punched is not None})
        # The broker's word rather than this half's: one end can have a socket the other end
        # never learned it had, and two halves disagreeing about which pipe the session is on
        # is a session that hangs with both of them certain they are right.
        agreed = lines.read(_ANSWERING).get("go")
        if agreed == "direct" and punched is not None:
            log.debug("joined %s directly", meeting.ticket[:8])
            home.close()
            return _settled(punched), asked
        if agreed != "relay":
            raise ConnectionError(  # noqa: TRY301 -- for the reason the one above is
                f"the broker will not join this session: {agreed}"
            )
        log.debug("joined %s through the broker", meeting.ticket[:8])
        if punched is not None:
            punched.close()
            punched = None
        _settled(home)
        held, home = home, None
        # The `except` below is a cleanup of the three sockets this call may be holding, and
        # an `else` after it would put the answer further from the road that reached it than
        # the two the branches above already are.
        return held, asked  # noqa: TRY300
    except BaseException:
        for spare in (home, ear, punched):
            if spare is not None:
                spare.close()
        raise
    finally:
        if ear is not None:
            ear.close()


# --------------------------------------------------------------------------- the broker


class Broker:
    """The meeting place: what humanize is to two machines that cannot reach each other.

    One object per listening address. Started once and left running, it costs a thread per
    half currently being introduced and nothing at all per session already under way -- a
    pair that was introduced is a pair this is no longer between.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",  # noqa: S104 -- the point is to be reachable from elsewhere
        port: int = 0,
        *,
        patience: float = PAIRING,
        punching: float = PUNCHING,
        booked: bool = False,
        tls: str = "",
    ) -> None:
        """Prepares a broker, without listening yet.

        Args:
          host: The address to listen on. Every interface by default: the halves being
            introduced are on other machines, which is the only reason this exists.
          port: The port, or 0 to be given one.
          patience: How long one half waits here for the other.
          punching: How long the two are given to reach each other before being carried.
          booked: Whether it introduces only the halves of meetings booked with it
            (:meth:`stand`), turning away every other ticket -- and counting what each
            address has connected without saying one (:data:`_KNOCKING`).
          tls: The directory holding its certificate and key, for a broker that speaks to
            nothing but TLS pinned to that certificate; "" for one in the clear.

        Raises:
          OSError: If its certificate or key cannot be read.
          ValueError: If either is not one, or the directory holds no key.
        """
        self._host = host
        self._port = port
        self._patience = patience
        self._punching = punching
        self._booked = booked
        self._tls = tls
        self._sealing = _sealing(tls) if tls else None
        if self._sealing is not None and self._sealing.server is None:
            raise ValueError(f"{tls} holds a certificate and no key to serve it with")
        self._lock = threading.Lock()
        #: The meetings still waiting for a half, by ticket, oldest first.
        self._meetings: dict[str, list[_Pair]] = {}
        #: The booked meetings, by their serving half's ticket, each with the key that half
        #: proved itself with the first time -- "" until it has come.
        self._serving: dict[str, str] = {}
        #: The same meetings by their anchoring halves' ticket.
        self._anchoring: dict[str, str] = {}
        #: How many halves each address has connected that have not yet been let in.
        self._knocking: dict[str, int] = {}
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._carried = 0
        self._failed: dict[tuple[str, str], int] = {}

    @property
    def carried(self) -> int:
        """How many sessions this broker had to carry rather than merely introduce.

        The number worth watching. Every session counted here is one paying this machine's
        bandwidth and this machine's latency for every byte, so a deployment whose count
        climbs with its session count is one where the punching never works and the two ends
        would be better off on a network that lets them meet.
        """
        return self._carried

    @property
    def tls(self) -> str:
        """The directory of the certificate it is pinned to, or "" for a broker in the clear.

        What a meeting held here is spelled with (:attr:`Meeting.tls`): as it is, for a half
        on this machine, which the key beside the certificate makes the server of a punched
        socket; and for a half elsewhere, wherever its :data:`CERTIFICATE` alone is put.
        """
        return self._tls

    @property
    def address(self) -> tuple[str, int]:
        """Where it is listening, as it was actually bound.

        Raises:
          RuntimeError: If it has not been started, there being no answer until it has.
        """
        if self._listener is None:
            raise RuntimeError("this broker has not been started")
        bound = self._listener.getsockname()
        return str(bound[0]), int(bound[1])

    def start(self) -> tuple[str, int]:
        """Begins listening and answering, and returns the address it landed on.

        Returns:
          The host and port, the port being a real one even where 0 was asked for.

        Raises:
          OSError: If the address cannot be listened on.
        """
        if self._listener is not None:
            return self.address
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self._host, self._port))
            # As deep a queue as the kernel will give. Both halves of every session arrive
            # here, and a run bringing a fleet up brings all of them up at once -- so what
            # queues at this socket is two connections per agent, arriving as fast as some
            # other machine can fork. A shallow backlog drops the overflow, and what that
            # looks like from a session is the other half never having arrived.
            listener.listen(_BACKLOG)
        except OSError:
            listener.close()
            raise
        self._listener = listener
        self._thread = threading.Thread(
            target=self._accept, name="rendezvous", daemon=True
        )
        self._thread.start()
        return self.address

    def stand(self) -> tuple[str, str]:
        """Books a meeting a serving half is left standing at, met again and again.

        Returns:
          Two tickets for it: the serving half's, which lets in that half alone -- the one
          that comes with it first, proving itself each time after by the key it came with --
          and the one every anchoring half meeting it is given.
        """
        serving, anchoring = ticket(), ticket()
        with self._lock:
            self._serving[serving] = ""
            self._anchoring[anchoring] = serving
        return serving, anchoring

    def withdraw(self, serving: str) -> None:
        """Cancels a booked meeting: neither of its tickets lets anybody in from now on.

        Args:
          serving: The serving half's ticket, as :meth:`stand` answered it.
        """
        with self._lock:
            self._serving.pop(serving, None)
            for anchoring in [k for k, v in self._anchoring.items() if v == serving]:
                del self._anchoring[anchoring]

    def close(self) -> None:
        """Stops listening. Sessions already introduced are not in this object's path."""
        self._closed.set()
        if self._listener is not None:
            with contextlib.suppress(OSError):
                self._listener.shutdown(socket.SHUT_RDWR)
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def serve_forever(self) -> None:
        """Starts it and stays here, which is what a broker run as a command line does."""
        host, port = self.start()
        log.info("rendezvous listening on %s:%s", host, port)
        with contextlib.suppress(KeyboardInterrupt):
            while not self._closed.wait(0.5):
                pass
        self.close()

    def _accept(self) -> None:
        assert self._listener is not None  # noqa: S101 -- set before this thread is started
        while not self._closed.is_set():
            try:
                half, whence = self._listener.accept()
            except OSError:
                return
            threading.Thread(
                target=self._introduce, args=(half, whence), daemon=True
            ).start()

    def _introduce(self, half: socket.socket, whence: tuple[str, int]) -> None:
        """Takes one half from its first word to its last, whichever way it ends."""
        pair: _Pair | None = None
        role = ""
        knocking = self._knock(whence[0])
        try:
            if knocking is None:
                return
            if self._sealing is not None:
                # Before a word is read: a half that will not speak TLS -- or speaks it to
                # somebody else's certificate -- is gone without having said anything.
                half = self._sealing.sealed(half, server=True, timeout=_ANSWERING)
            lines = _Lines(half)
            hello = lines.read(_ANSWERING)
            name, role = str(hello.get("ticket", "")), str(hello.get("role", ""))
            asks = _asked(hello.get("export")) if role == ANCHOR else ()
            if not name or role not in ROLES or asks is None:
                _say(half, {"go": "no", "why": "say a ticket and a role"})
                return
            let_in = self._admitted(name, role, str(hello.get("key") or ""))
            if let_in is None:
                _say(half, {"go": "no", "why": "no meeting here lets that half in"})
                return
            name, booked = let_in
            self._unknock(knocking)
            knocking = None
            # Its own address as the world has it, which is the one fact about a machine
            # behind a NAT that only somebody outside it can supply.
            _say(half, {"seen": [whence[0], whence[1]]})
            mine = [*_pairs(hello.get("at")), (whence[0], whence[1])]
            joined_at = self._join(name, role, half, mine, asks)
            if isinstance(joined_at, str):
                _say(half, {"go": "no", "why": joined_at})
                return
            pair = joined_at
            other = pair.await_other(role, self._patience)
            if other is None and not self._withdrawn(pair):
                # Met in the instant it gave up: whoever took it off the queue has arrived.
                other = pair.await_other(role, 0.0)
            if other is None:
                _say(half, {"go": "no", "why": "the other half never arrived"})
                return
            between = pair.between()
            punching = self._punching if self._worth(between) else 0.0
            said: dict[str, Any] = {"peer": other, "punch": punching}
            if booked:
                # Its two halves hold two tickets, so neither can prove the other's.
                said["proof"] = pair.proof
            if role == SERVE and pair.asks:
                said["export"] = list(pair.asks)
            _say(half, said)
            direct = bool(lines.read(punching + _ANSWERING).get("direct"))
            joined = pair.settle(role, direct=direct, patience=_ANSWERING)
            if role == ANCHOR:
                # Before the half is told, so that what this pair came to is what the next
                # pair of the same two machines is judged by, however soon that one comes.
                self._learn(between, worked=joined)
                if not joined:
                    self._carried += 1
            _say(half, {"go": "direct" if joined else "relay"})
            pair.spoke(role)
            if not joined:
                pair.carry(role)
        except (OSError, ValueError) as exc:
            log.debug("a half of %s left: %s", role or "a meeting", exc)
        finally:
            if knocking is not None:
                self._unknock(knocking)
            if pair is not None:
                self._forget(pair, role)
            with contextlib.suppress(OSError):
                half.close()

    def _knock(self, address: str) -> str | None:
        """Counts a half connected from an address, until it is let in or goes.

        Returns:
          The address to stop counting it under, "" for one not counted -- every half of a
          broker that books nothing, and those of this machine's own -- or None for a half
          refused for there already being :data:`_KNOCKING` from there.
        """
        if not self._booked or address in (self._host, "127.0.0.1"):
            return ""
        with self._lock:
            if self._knocking.get(address, 0) >= _KNOCKING:
                return None
            self._knocking[address] = self._knocking.get(address, 0) + 1
        return address

    def _unknock(self, address: str) -> None:
        """Stops counting a half :meth:`_knock` counted."""
        if not address:
            return
        with self._lock:
            left = self._knocking.get(address, 0) - 1
            if left > 0:
                self._knocking[address] = left
            else:
                self._knocking.pop(address, None)

    def _admitted(self, name: str, role: str, key: str) -> tuple[str, bool] | None:
        """The meeting a half is let into, and whether it is a booked one.

        A booked meeting is waited at under its serving half's ticket, which lets in a
        serving half alone, and of those only the one that first came with it -- the key it
        came with being what every later one is held to. Its anchoring halves come with the
        other ticket and are let into the same meeting.

        Args:
          name: The ticket the half came with.
          role: Which half it says it is.
          key: What it proves itself with, "" for nothing.

        Returns:
          The meeting's name and whether it was booked, or None for a half let in nowhere.
        """
        with self._lock:
            serving = self._anchoring.get(name)
            if serving is not None:
                return (serving, True) if role == ANCHOR else None
            if name in self._serving:
                if role != SERVE or not key:
                    return None
                held = self._serving[name]
                if not held:
                    self._serving[name] = key
                elif not hmac.compare_digest(held.encode(), key.encode()):
                    return None
                return name, True
        return None if self._booked else (name, False)

    def _worth(self, between: tuple[str, str] | None) -> bool:
        """Whether these two are worth trying to introduce, or have failed too lately.

        Args:
          between: The two machines, as the world addresses them, or None where that is not
            yet known -- which is always worth a try.

        Returns:
          True to spend the window, False to carry them without spending it.
        """
        if between is None:
            return True
        with self._lock:
            failed = self._failed.get(between, 0)
        # And every so often after that, because a firewall rule is the kind of thing that
        # changes: the modulus answers the attempt *after* the sixteenth failure, and after
        # every sixteenth one since.
        return failed < _CONVINCED or failed % _DISBELIEVING == 0

    def _learn(self, between: tuple[str, str] | None, *, worked: bool) -> None:
        """Remembers how that went, so the next pair of these two need not find out again."""
        if between is None:
            return
        with self._lock:
            if worked:
                self._failed.pop(between, None)
            elif between in self._failed or len(self._failed) < _HOPELESS:
                self._failed[between] = self._failed.get(between, 0) + 1

    def _join(
        self,
        name: str,
        role: str,
        half: socket.socket,
        mine: list[tuple[str, int]],
        asks: tuple[str, ...] = (),
    ) -> _Pair | str:
        """Puts one half into the oldest meeting waiting for it, else into one of its own.

        A meeting given its second half is taken off the queue there and then, so the next
        half under the ticket starts the next meeting; and both are under the lock, so a half
        giving up can tell whether it was met as it did.

        Returns:
          The meeting, or why there is none to be had.
        """
        with self._lock:
            waiting = self._meetings.get(name, [])
            if waiting and role not in waiting[0].halves:
                pair = waiting.pop(0)
                if not waiting:
                    del self._meetings[name]
            elif not waiting and len(self._meetings) >= _TICKETS:
                return f"this rendezvous is already holding {_TICKETS} meetings"
            elif len(waiting) >= _QUEUED:
                return f"this ticket already has {_QUEUED} meetings waiting"
            else:
                pair = _Pair(name)
                self._meetings.setdefault(name, []).append(pair)
            if role == ANCHOR:
                pair.asks = asks
            pair.arrive(role, half, mine)
        return pair

    def _withdrawn(self, pair: _Pair) -> bool:
        """Takes a meeting off the queue, and says whether it was still on it."""
        with self._lock:
            waiting = self._meetings.get(pair.name, [])
            if pair not in waiting:
                return False
            waiting.remove(pair)
            if not waiting:
                del self._meetings[pair.name]
            return True

    def _forget(self, pair: _Pair, role: str) -> None:
        """Lets one half go, off the queue first so that nothing finds it half gone."""
        self._withdrawn(pair)
        pair.leave(role)


@dataclass(eq=False)
class _Pair:
    """One meeting: the two halves of it, and everything either is waiting on the other for.

    Told apart by identity, which is what a queue of them is searched by.
    """

    name: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    halves: dict[str, socket.socket] = field(default_factory=dict[str, socket.socket])
    theirs: dict[str, list[tuple[str, int]]] = field(
        default_factory=dict[str, list[tuple[str, int]]]
    )
    verdicts: dict[str, bool] = field(default_factory=dict[str, bool])
    #: What the anchoring half asked to be served, which its serving half is told.
    asks: tuple[str, ...] = ()
    #: What the two prove to each other on a punched socket, where they hold two tickets.
    proof: str = field(default_factory=lambda: secrets.token_hex(16))
    #: Where each half is as the broker saw it, which is how a pair of machines is named.
    seen: dict[str, str] = field(default_factory=dict[str, str])
    #: Set when the half of that name has said what it is and where it can be reached.
    arrived: dict[str, threading.Event] = field(
        default_factory=lambda: {role: threading.Event() for role in ROLES}
    )
    #: Set when it has said whether it got through.
    answered: dict[str, threading.Event] = field(
        default_factory=lambda: {role: threading.Event() for role in ROLES}
    )
    #: Set once that half has been told how the session will be joined. The two halves are
    #: answered by two threads and nothing else orders them, so this is what keeps the one
    #: that carries the bytes from starting before the other has been spoken to.
    told: dict[str, threading.Event] = field(
        default_factory=lambda: {role: threading.Event() for role in ROLES}
    )
    #: Set once the bytes have finished flowing, for whichever thread is not carrying them.
    done: threading.Event = field(default_factory=threading.Event)
    #: How the two are joined -- direct or not -- once the first of them has been told.
    joined: bool | None = None

    def arrive(
        self, role: str, half: socket.socket, mine: list[tuple[str, int]]
    ) -> None:
        with self.lock:
            self.halves[role] = half
            self.theirs[role] = mine
            # The last of them is the one the world has, this being the order a half offers
            # its addresses in and the broker's own view of it being what it appends.
            self.seen[role] = mine[-1][0] if mine else ""
        self.arrived[role].set()

    def between(self) -> tuple[str, str] | None:
        """The two machines this meeting is between, as the world addresses them.

        Sorted, so that the pair is the pair whichever of them arrived first, and by address
        alone: the port a half was seen at is this session's and says nothing about the next.

        Returns:
          The two, or None if both have not yet said anything.
        """
        with self.lock:
            if len(self.seen) != len(ROLES):
                return None
            one, other = sorted(self.seen.values())
        return (one, other)

    def await_other(self, role: str, patience: float) -> list[tuple[str, int]] | None:
        """Waits for the other half and answers with the addresses it may be reached at."""
        if not self.arrived[_OPPOSITE[role]].wait(patience):
            return None
        with self.lock:
            return self.theirs.get(_OPPOSITE[role])

    def settle(self, role: str, *, direct: bool, patience: float) -> bool:
        """Answers whether the session is theirs to carry, which needs both to say so.

        One end holding a socket the other end never saw is the case this exists for: the
        anchoring half can have sent its choice into a hole that closed, and a pair that
        disagrees is a pair that hangs. So both verdicts are collected and the answer is the
        weaker of the two, for both of them -- decided once, by whichever is told first: a
        half that gave up waiting for the other has been told the session is carried, and the
        late one, finding both verdicts in, must be told the same rather than work it out
        again.
        """
        with self.lock:
            self.verdicts[role] = direct
        self.answered[role].set()
        heard = self.answered[_OPPOSITE[role]].wait(patience)
        with self.lock:
            if self.joined is None:
                self.joined = heard and all(
                    self.verdicts.get(name, False) for name in ROLES
                )
            return self.joined

    def spoke(self, role: str) -> None:
        """Says that half has been told how the session will be joined."""
        self.told[role].set()

    def carry(self, role: str) -> None:
        """Moves the bytes between the two, for a pair that could not be introduced.

        One of the two threads does the carrying and the other waits for it, so that neither
        socket is closed from under the splice by the half that stopped having anything to do.

        And the carrying waits until both halves have been spoken to. The two are answered by
        two threads with nothing ordering them, so the one that carries can reach here while
        the *other* half has not yet been sent the line saying a splice is coming -- and the
        first bytes of the session would then arrive where that half is still reading a
        control line, one character at a time, out of a frame. There is no recovering from
        that and no recognising it: the stream is simply shifted from then on.
        """
        if role != ANCHOR:
            self.done.wait(timeout=None)
            return
        self.told[_OPPOSITE[ANCHOR]].wait(timeout=_ANSWERING)
        with self.lock:
            here, there = self.halves.get(ANCHOR), self.halves.get(SERVE)
        try:
            if here is not None and there is not None:
                _splice(here, there)
        finally:
            self.done.set()

    def leave(self, role: str) -> bool:
        """Takes one half out, and says whether that was the last of them."""
        # Whoever goes first releases the other from waiting on a splice that is not coming.
        self.done.set()
        self.told[role].set()
        self.answered[role].set()
        self.arrived[role].set()
        with self.lock:
            self.halves.pop(role, None)
            return not self.halves


def _splice(one: socket.socket, two: socket.socket) -> None:
    """Carries bytes each way until both ends have stopped, then shuts the two down.

    A thread per direction rather than one loop over both, and deliberately. A single loop
    that is blocked writing one way is a loop not reading the other, so two ends that are
    both mid-transfer -- a file going across while output comes back, which for a coding
    agent is most of a turn -- can arrive at each waiting on the other. Two threads cannot do
    that to each other, and two threads is the whole of what a carried session costs here.
    """
    for end in (one, two):
        # Both of them, and before either thread starts. These sockets have been carrying the
        # introduction, which is read a line at a time under a deadline, so each of them is
        # still holding whatever timeout the last line left on it. A `sendall` that timed out
        # mid-frame would have sent *part* of one -- and the far side would read the rest of
        # the session shifted by however many bytes were lost, which is not an error it can
        # recover from or even recognise. Blocking, always, once this is a pipe.
        end.settimeout(None)
    moving = [
        threading.Thread(target=_pour, args=(source, sink), daemon=True)
        for source, sink in ((one, two), (two, one))
    ]
    for thread in moving:
        thread.start()
    for thread in moving:
        thread.join()
    for end in (one, two):
        with contextlib.suppress(OSError):
            end.shutdown(socket.SHUT_RDWR)


def _pour(source: socket.socket, sink: socket.socket) -> None:
    """Moves everything one way, and tells the far end when there is no more of it.

    The half-close is the point of the `finally`: one direction ending is not the session
    ending, and a peer waiting to read the last of what it was sent has to be told that is
    the last of it rather than left holding a connection nothing more is coming down.

    Both sockets are blocking by the time this runs -- :func:`_splice` says why that matters.
    """
    try:
        while True:
            moving = source.recv(_RELAY)
            if not moving:
                return
            sink.sendall(moving)
    except OSError:
        return
    finally:
        with contextlib.suppress(OSError):
            sink.shutdown(socket.SHUT_WR)


# ------------------------------------------------------------------- the broker humanize is


#: The one this process runs, made when something first needs it and kept afterwards. A
#: broker is a listening socket and a thread per introduction in flight, so a run that
#: anchors a hundred turns across a dozen machines pays for one of them.
_here: Broker | None = None
_SHARING = threading.Lock()


def shared(advertise: str = "") -> tuple[Broker, str, int]:
    """The broker this process holds, started on first use and kept for the rest of the run.

    Args:
      advertise: The address the two halves should dial, for a machine whose own name is not
        the one they can reach it by. Empty asks this machine which of its addresses faces
        outward, which is right wherever the halves are on the same network as this one.

    Returns:
      The broker, and the host and port to hand the halves.

    Raises:
      OSError: If it cannot listen.
    """
    global _here  # noqa: PLW0603 -- one per process is the point
    with _SHARING:
        if _here is None:
            broker = Broker(port=int(os.environ.get("HUMANIZE_RENDEZVOUS_PORT", "0")))
            broker.start()
            _here = broker
        _, port = _here.address
        return (
            _here,
            advertise or os.environ.get("HUMANIZE_RENDEZVOUS") or _facing(),
            port,
        )


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


#: The brokers this process holds for booked meetings, by the address their halves dial.
_standings: dict[str, Broker] = {}


def standing(address: str) -> tuple[Broker, int]:
    """The broker this process holds for the meetings it books, dialled at `address`.

    Apart from :func:`shared`'s, and stricter: it introduces only the halves of meetings
    booked with it (:meth:`Broker.stand`), and listens on that address alone where it is one
    of this machine's -- not on every interface, for any ticket anybody brings. Where it is
    not -- the address of a NAT in front of this machine, or a name only the other side
    resolves -- on every interface, as :func:`shared`'s does.

    And sealed (:attr:`Broker.tls`), always: its meetings are with machines that are not
    this one, over networks nothing here vouches for. Its key and certificate are made for it
    -- for this run, that is -- under :func:`hmz.machine`, which is this machine's alone and
    nobody else's to read, and are removed as the run ends. One per run rather than one kept
    per runtime: a key that lives exactly as long as the one broker that uses it and the
    tasks pinned to it -- which go with the run, or with the next one -- has nothing to
    rotate, nothing to revoke, and nothing left to be worth anything to whoever finds it.

    Args:
      address: Where the serving halves reach this machine.

    Returns:
      The broker, started on first use and kept for the rest of the run, and its port.

    Raises:
      FileNotFoundError: If there is no `openssl` here to make its certificate with.
      OSError: If it cannot listen, or its certificate could not be made.
    """
    with _SHARING:
        broker = _standings.get(address)
        if broker is None:
            port = int(os.environ.get("HUMANIZE_RENDEZVOUS_PORT", "0"))
            sealed = _minted()
            broker = Broker(address, port, booked=True, tls=sealed)
            try:
                broker.start()
            except OSError as error:
                if not isinstance(error, socket.gaierror) and (
                    error.errno != errno.EADDRNOTAVAIL
                ):
                    raise
                broker = Broker(port=port, booked=True, tls=sealed)
                broker.start()
            _standings[address] = broker
        return broker, broker.address[1]


def _minted() -> str:
    """A directory only this user may enter, holding a key and a certificate made for it.

    Made by `openssl`, which is wherever docker is, rather than by a cryptography package
    humanize would otherwise carry for this alone; and with no name, no authority and no
    extension in it worth checking, since nothing checks anything of it but that it is the
    very certificate it is.

    Returns:
      The directory, named for this process, which is removed when it exits -- or, when it
      was killed before it could, by the next process making one.

    Raises:
      FileNotFoundError: If there is no `openssl` here.
      OSError: If it could not make them.
    """
    import atexit
    import shutil
    import subprocess
    import tempfile

    from hmz import machine

    home = machine()
    _unminted(home)
    made = Path(tempfile.mkdtemp(prefix=f"rendezvous-{os.getpid()}-", dir=home))
    atexit.register(shutil.rmtree, made, ignore_errors=True)
    try:
        subprocess.run(
            [
                *("openssl", "req", "-x509", "-nodes", "-days", "365"),
                *("-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1"),
                *("-subj", "/CN=humanize rendezvous"),
                *("-keyout", str(made / _KEY), "-out", str(made / CERTIFICATE)),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=True,
            # The key is this user's from the instant it exists, not from a chmod after.
            umask=0o077,
        )
    except FileNotFoundError as error:
        raise FileNotFoundError(
            errno.ENOENT, "no openssl command here", "openssl"
        ) from error
    except subprocess.CalledProcessError as error:
        raise OSError(
            f"openssl could not make a certificate: {error.stderr.strip()}"
        ) from error
    return str(made)


def _unminted(home: Path) -> None:
    """Removes the key and certificate of every broker whose process has gone.

    A process removes its own as it exits, which a process killed never gets to: its key
    would stay, readable by nobody else but no longer anybody's, until something takes it.

    Args:
      home: Where they are made, this machine's own directory for this user.
    """
    import shutil

    for one in home.glob("rendezvous-*-*"):
        pid = one.name.split("-")[1]
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            shutil.rmtree(one, ignore_errors=True)
        except OSError:
            continue  # somebody's, still running


# ------------------------------------------------------------------------ punching a hole


def _punch(
    ear: socket.socket | None,
    port: int,
    candidates: list[Any],
    name: str,
    role: str,
    seconds: float,
    sealing: _Sealing | None = None,
) -> socket.socket | None:
    """Opens holes at every address the other half gave, and listens for its own.

    Every candidate is tried at once and repeatedly, because a punch is two attempts crossing
    in flight: the first outbound packet is what opens the way for the peer's, and which
    attempt that turns out to be is not something either side can arrange. The first
    connection that proves it is the other half of this session is the one kept; the rest are
    closed where they stand.

    Args:
      ear: The listening socket on the shared port, or None where the kernel would not lend
        the port twice -- such a half punches outward only.
      port: The port to open outward from, which is the one the peer was told about.
      candidates: Where the other half may be, as `[host, port]` pairs.
      name: The ticket, which neither half puts on the wire.
      role: Which half this is.
      seconds: How long to keep trying.
      sealing: For a sealed meeting, the TLS every punched socket is to be held in.

    Returns:
      The socket joining the two, or None if the window closed with nothing through it.
    """
    where_to = _pairs(candidates)
    if not where_to and ear is None:
        return None
    deadline = time.monotonic() + seconds
    won: queue.Queue[socket.socket] = queue.Queue()
    # A latch rather than a flag, because reading it and setting it have to be one thing: two
    # connections can get through at once -- each half knocks while it listens, so a pair that
    # punches cleanly makes two -- and two threads that both found it clear would both accept,
    # leaving the two halves holding one end each of *different* sockets. Taken once, never
    # given back; whoever gets it is the connection this session is.
    claimed = threading.Lock()
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=_knocking,
            args=(where, port, name, role, sealing, won, claimed, stop, deadline),
            daemon=True,
        )
        for where in where_to
    ]
    if ear is not None:
        threads.append(
            threading.Thread(
                target=_answering,
                args=(ear, name, role, sealing, won, claimed, stop, deadline),
                daemon=True,
            )
        )
    for thread in threads:
        thread.start()
    try:
        return won.get(timeout=max(0.0, deadline - time.monotonic()))
    except queue.Empty:
        return None
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=0.5)
        # Anything that arrived after the winner is a socket nobody is going to read.
        while True:
            try:
                won.get_nowait().close()
            except queue.Empty:
                break


def _knocking(
    where: tuple[str, int],
    port: int,
    name: str,
    role: str,
    sealing: _Sealing | None,
    won: queue.Queue[socket.socket],
    claimed: threading.Lock,
    stop: threading.Event,
    deadline: float,
) -> None:
    """Keeps opening outward at one candidate until something answers or time runs out."""
    while not stop.is_set() and time.monotonic() < deadline:
        knock = _outward()
        try:
            try:
                knock.bind(("", port))
            except OSError:
                # Somebody else has this half's own port and this moment. Knock from wherever
                # the kernel will have us instead: the hole it opens is at a different port,
                # so a NAT in the way will not be punched through -- but a peer on the same
                # network is reached all the same, and the alternative is not knocking.
                knock.bind(("", 0))
            knock.settimeout(max(0.2, min(1.0, deadline - time.monotonic())))
            knock.connect(where)
        except OSError as exc:
            knock.close()
            log.debug("knocked at %s and got %s", where, exc)
            # A beat before the next one: a refused connection is instant, and a tight loop
            # on it would spend the window on syscalls rather than on giving the other half
            # time to open its own side.
            stop.wait(0.05)
            continue
        log.debug("opened outward to %s", where)
        _greet(knock, name, role, sealing, won, claimed)
        return


def _answering(
    ear: socket.socket,
    name: str,
    role: str,
    sealing: _Sealing | None,
    won: queue.Queue[socket.socket],
    claimed: threading.Lock,
    stop: threading.Event,
    deadline: float,
) -> None:
    """Greets whatever arrives on the shared port, which is where the peer's punch lands."""
    while not stop.is_set() and time.monotonic() < deadline:
        ear.settimeout(max(0.1, min(0.5, deadline - time.monotonic())))
        try:
            arrived, _ = ear.accept()
        except (TimeoutError, OSError):
            continue
        log.debug("something arrived on the shared port")
        threading.Thread(
            target=_greet,
            args=(arrived, name, role, sealing, won, claimed),
            daemon=True,
        ).start()


def _greet(
    punched: socket.socket,
    name: str,
    role: str,
    sealing: _Sealing | None,
    won: queue.Queue[socket.socket],
    claimed: threading.Lock,
) -> None:
    """Proves a connection is the other half of this session, and settles who keeps it.

    Both ends say the same thing first -- this protocol, a digest of the secret bound to which
    half they are, which half they are -- so a connection to anything else, and a connection
    to one's own listener, is over before either end has told it anything. Bound to the half,
    so that what one end says cannot be said back to it: whoever reaches a listening half
    hears that half's proof, and must still answer with the other's. What follows decides
    between the several sockets that may have got through at once: the anchoring half offers
    each one it has and the serving half accepts exactly one, which is an agreement neither
    can reach alone.

    On a sealed meeting all of it is said inside TLS, of which the anchoring half is the
    server, whichever end dialled: its machine holds the key, and a serving half greets only
    a socket presenting the certificate it was handed.
    """
    kept = False
    try:
        if sealing is not None:
            punched = sealing.sealed(punched, server=role == ANCHOR, timeout=GREETING)
        punched.settimeout(GREETING)
        punched.sendall(b" ".join((_MAGIC, _proof(name, role), role.encode())) + b"\n")
        other = _OPPOSITE[role]
        if _line(punched, GREETING).split() != [
            _MAGIC,
            _proof(name, other),
            other.encode(),
        ]:
            return
        if role == ANCHOR:
            punched.sendall(_GO + b"\n")
            if _line(punched, GREETING).split()[:1] != [_OK]:
                return
        else:
            if _line(punched, GREETING).split()[:1] != [_GO]:
                return
            # The serving half is the one that decides, because it is the one that can see
            # every offer: whichever GO it reads first is the socket, and its OK is what
            # tells that anchor thread it won while the others hear nothing and give up.
            # Tested and taken in one step, so that two offers arriving together cannot both
            # be answered -- which would leave the two halves on two different sockets, each
            # certain it had been agreed to.
            if not claimed.acquire(blocking=False):
                return
            punched.sendall(_OK + b"\n")
        kept = True
        won.put(punched)
    except (OSError, ValueError, IndexError) as exc:
        log.debug("a greeting came to nothing: %s", exc)
        return
    finally:
        if not kept:
            # Closed where it lost rather than gathered up afterwards: this may be running in
            # a thread nothing is waiting on, and a socket left for somebody else to sweep is
            # one nobody sweeps.
            punched.close()


def _proof(name: str, role: str) -> bytes:
    """What a half proves on a punched socket: that it knows the secret, and is that half."""
    return hmac.new(name.encode(), role.encode(), hashlib.sha256).hexdigest().encode()


# ------------------------------------------------------------------------------- sockets


def _outward() -> socket.socket:
    """A socket that may share the port every other socket of this session is using.

    Both halves open outward from, and listen on, the one port the broker saw them at. That
    is several sockets on one local address at once, which the kernel allows only for a socket
    that asked -- so every one of them asks, here, in one place.
    """
    made = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    made.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        with contextlib.suppress(OSError):
            made.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    return made


def _both() -> tuple[socket.socket, socket.socket | None, int]:
    """A socket to dial the broker from and a listener, sharing one port.

    The listener is bound *first* and the dialling socket is bound to the port it landed on,
    which is the opposite of the obvious order and is the whole of what makes this reliable.
    Taking an ephemeral port by connecting and then asking for it again is a race: the second
    bind can lose, and a half that lost it can neither be reached nor reach out -- every one
    of its own knocks is bound to the same port and fails the same way. A window then passes
    with nothing through it, and a pair that could have met perfectly well is carried instead.
    Binding the listener first makes the one socket that must exist the one that is never in
    doubt, and the second bind is retried a few times before it is given up on.

    Returns:
      The socket to dial the broker from, the listener or None if the port could not be
      shared after all, and the port the two of them are on. A half with no listener still
      punches outward and is still worth introducing; it simply cannot be knocked at.
    """
    for _ in range(_TRIES):
        ear = _outward()
        try:
            ear.bind(("", 0))
            ear.listen(8)
            port = int(ear.getsockname()[1])
            home = _outward()
            try:
                home.bind(("", port))
            except OSError:
                home.close()
                raise
        except OSError as exc:
            log.debug("could not take a port for both halves of a punch: %s", exc)
            ear.close()
            continue
        return home, ear, port
    # Nothing shareable to be had. The broker still sees this half at wherever it dials from,
    # and its own knocks still open holes; it is only the listening that is lost.
    home = _outward()
    home.bind(("", 0))
    return home, None, int(home.getsockname()[1])


def _settled(held: socket.socket) -> socket.socket:
    """Hands a socket on as the session wants it: blocking, with nothing timing it out.

    And sending at once, where it is the connection itself; a sealed one is a socket of this
    machine's own, whose connection :meth:`_Sealing.sealed` has already told the same.
    """
    held.settimeout(None)
    if held.family == socket.AF_INET:
        held.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return held


def _mine(home: socket.socket, port: int) -> list[tuple[str, int]]:
    """Where this half says it can be reached, before the broker adds what it saw.

    The address this machine reached the broker from comes first, being the one it would be
    reached back at by anything on the same network; its other names follow, for the case
    where the broker is somewhere else entirely and the two halves are neighbours.
    """
    addresses = [str(home.getsockname()[0])]
    for address in _named(port):
        if address not in addresses:
            addresses.append(address)
    return [(address, port) for address in addresses]


def _named(port: int) -> list[str]:
    """This machine's addresses by its own name, or none if the name is slow to say them.

    Asked of the resolver, which may not know the name at all: a Mac's `<name>.local` is
    looked up over multicast DNS and, where nothing answers, takes over half a minute to fail
    -- longer than the broker waits for this half's first word, so a half that waited for it
    would arrive to find the broker gone. The names are a nicety for neighbours, and are left
    out rather than waited for.
    """
    found: list[str] = []
    done = threading.Event()

    def asking() -> None:
        with contextlib.suppress(OSError):
            found.extend(
                str(one[4][0])
                for one in socket.getaddrinfo(
                    socket.gethostname(), port, socket.AF_INET, socket.SOCK_STREAM
                )
            )
        done.set()

    threading.Thread(target=asking, name="rendezvous-names", daemon=True).start()
    return list(found) if done.wait(_NAMING) else []


def _pairs(said: Any) -> list[tuple[str, int]]:
    """Reads a candidate list off the wire, keeping only the addresses that can be punched to.

    One reader for both ends. The broker passes on what a half claimed for itself and a half
    dials what it was passed, so a shape one of them accepted and the other threw away would
    be a candidate that spends a window without ever having been reachable.

    Deduplicated, because a half's own list and what the broker saw of it overlap by design,
    and a duplicate is a thread knocking at an address another thread is already knocking at.
    IPv4 only, for the reason the module says: one port, one socket, one family.
    """
    found: dict[tuple[str, int], None] = {}
    for entry in cast("list[Any]", said) if isinstance(said, list) else ():
        pair = cast("list[Any]", entry) if isinstance(entry, list) else []
        if len(pair) != 2 or not isinstance(pair[1], int):  # noqa: PLR2004
            continue
        host = str(pair[0])
        with contextlib.suppress(OSError):
            socket.inet_aton(host)
            found[host, pair[1]] = None
    return list(found)


def _asked(said: Any) -> tuple[str, ...] | None:
    """Reads the directories an anchoring half asked for off the wire.

    One reader for both ends, as :func:`_pairs` is: the broker keeps what a half said and the
    other half is passed it. Bounded, since it is held for as long as the meeting is waited
    at.

    Returns:
      What was asked; empty where nothing was. None for something that is not a list of
      directories, which is refused rather than read as having asked for nothing -- a
      session that asked for nothing is served everything.
    """
    if said is None:
        return ()
    if not isinstance(said, list):
        return None
    asked = cast("list[Any]", said)
    if len(asked) > _ASKS or not all(
        isinstance(one, str) and 0 < len(one) <= _ASKED for one in asked
    ):
        return None
    return tuple(cast("list[str]", asked))


# ------------------------------------------------------------------------------- sealing


@dataclass(frozen=True, slots=True)
class _Sealing:
    """TLS for the meetings of one certificate, pinned to that certificate byte for byte.

    No authority vouches for it and no name is checked against it. It was made for one
    broker of one run and handed to each half by whoever started that half, so whether a peer
    presented *it* is the whole question -- and a peer can only present it by holding its key,
    which the TLS handshake makes it prove. That is also why the chain is not verified: a lone
    self-signed certificate is judged differently by each OpenSSL and each Python's strictness
    about its extensions, and the answer to the one question that matters is the same in all
    of them.

    Attributes:
      pinned: The certificate, DER-encoded, as a peer must present it.
      client: The context a half that checks the other is sealed with.
      server: The context a half holding the key is sealed with; None where it holds none.
    """

    pinned: bytes
    client: ssl.SSLContext
    server: ssl.SSLContext | None

    def sealed(
        self, raw: socket.socket, *, server: bool, timeout: float
    ) -> socket.socket:
        """Holds a connection in TLS, and answers with a socket carrying what it opens.

        The handshake is done here, within `timeout`; from then on one thread of its own does
        everything TLS on the connection (:func:`_pump`), and the socket answered is one end
        of a pair of this machine's, the thread holding the other -- a socket like any other,
        which this module's lines, its relay and the session above can each use as they
        would the connection itself.

        Args:
          raw: The connection, which is the answer's from here on and closed with it, or
            closed here if it cannot be sealed.
          server: Whether this end serves the certificate -- and so must hold its key --
            rather than checking the other end's against it.
          timeout: How long the handshake may take.

        Returns:
          The socket carrying the connection's plaintext.

        Raises:
          OSError: If the handshake fails or does not finish in time, the other end is not
            speaking TLS, or -- checking -- what it presented is not the certificate pinned.
          ValueError: If this end is to serve the certificate and holds no key.
        """
        context = self.server if server else self.client
        if context is None:
            raw.close()
            raise ValueError("this half holds no key to serve its meeting's TLS with")
        inbound, outbound = ssl.MemoryBIO(), ssl.MemoryBIO()
        tls = context.wrap_bio(inbound, outbound, server_side=server)
        try:
            _handshake(
                raw,
                tls,
                (inbound, outbound),
                pinned=None if server else self.pinned,
                timeout=timeout,
            )
        except BaseException:
            raw.close()
            raise
        mine, theirs = socket.socketpair()
        threading.Thread(
            target=_pump,
            args=(raw, tls, inbound, outbound, theirs),
            name="rendezvous-tls",
            daemon=True,
        ).start()
        return mine


def _handshake(
    raw: socket.socket,
    tls: ssl.SSLObject,
    bios: tuple[ssl.MemoryBIO, ssl.MemoryBIO],
    *,
    pinned: bytes | None,
    timeout: float,
) -> None:
    """Shakes hands over a connection, checking what the other end presented where asked.

    Raises:
      OSError: If it fails or does not finish within `timeout`, or the other end presented a
        certificate other than `pinned`.
    """
    inbound, outbound = bios
    ends = time.monotonic() + timeout
    while not _shaken(tls):
        raw.settimeout(max(0.01, ends - time.monotonic()))
        raw.sendall(outbound.read())
        heard = raw.recv(_RELAY)
        if not heard:
            raise ConnectionError("the other end left during the TLS handshake")
        inbound.write(heard)
    raw.settimeout(max(0.01, ends - time.monotonic()))
    raw.sendall(outbound.read())
    if pinned is not None and tls.getpeercert(binary_form=True) != pinned:
        raise ConnectionError(
            "the other end presented a certificate other than this meeting's"
        )
    raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def _shaken(tls: ssl.SSLObject) -> bool:
    """Takes a handshake as far as what has arrived allows, and says whether it is done."""
    try:
        tls.do_handshake()
    except ssl.SSLWantReadError:
        return False
    return True


@functools.cache
def _sealing(at: str) -> _Sealing:
    """The TLS of the meetings whose directory is `at`, read once per process.

    Args:
      at: The directory holding the :data:`CERTIFICATE` -- and, where this machine serves it,
        the key.

    Returns:
      What the meetings are sealed with.

    Raises:
      OSError: If the certificate cannot be read, or the key is there and cannot be.
      ValueError: If the certificate is not one.
    """
    certificate = Path(at) / CERTIFICATE
    pinned = ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding="ascii"))
    client = _context(server=False)
    # Pinned rather than verified, and so neither named nor chained: see `_Sealing`.
    client.check_hostname = False
    client.verify_mode = ssl.CERT_NONE
    server = None
    if (Path(at) / _KEY).exists():
        server = _context(server=True)
        # Nothing is resumed: every connection is a handshake of its own.
        server.num_tickets = 0
        server.load_cert_chain(certificate, Path(at) / _KEY)
    return _Sealing(pinned, client, server)


def _context(*, server: bool) -> ssl.SSLContext:
    """A context of TLS 1.3 at least, which every Python this runs on has."""
    context = ssl.SSLContext(
        ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return context


def _pump(
    raw: socket.socket,
    tls: ssl.SSLObject,
    inbound: ssl.MemoryBIO,
    outbound: ssl.MemoryBIO,
    plain: socket.socket,
) -> None:
    """Carries one sealed connection's plaintext to and from the socket handed on for it.

    One thread for both directions, and that is the point of it. OpenSSL's state for one
    connection is not to be read in one thread while another writes it, and everything that
    uses a socket here does exactly that -- a session reading in one thread while commands are
    sent in others, a relay pouring each way in a thread apiece. So nothing but this thread
    touches the TLS, and what they all use is a socket of this machine's own.

    The ends are kept as a socket keeps them. The other end's close_notify -- or its going
    away -- is the end of what it sends, and the plain socket is shut for writing once the last
    of that has been handed over, while whatever is still written to it is still sealed and
    sent. The plain socket's own end is this one's: everything written before it is sealed
    and sent, followed by a close_notify, and the connection is let go (:func:`_letting_go`).
    A connection that fails -- a record that does not decrypt, which is somebody tampering --
    is dropped at once, and the plain socket with it.
    """
    raw.settimeout(0.0)
    plain.settimeout(0.0)
    sending = bytearray()  # sealed, for the wire
    handing = bytearray()  # opened, for the plain socket
    heard = drained = shut = False
    try:
        while True:
            while not heard and len(handing) < _RELAY:
                try:
                    opened = tls.read(_RELAY)
                except ssl.SSLWantReadError:
                    break
                except (ssl.SSLZeroReturnError, ssl.SSLEOFError):
                    opened = b""
                handing += opened
                heard = not opened
            # Stopped for want of room rather than of records: what TLS still holds has
            # arrived already, and no socket will say so again.
            full = not heard and len(handing) >= _RELAY
            sending += outbound.read()
            if handing:
                del handing[: _sent(plain, handing)]
            if heard and not handing and not shut:
                plain.shutdown(socket.SHUT_WR)
                shut = True
            if sending:
                del sending[: _sent(raw, sending)]
            if full and len(handing) < _RELAY:
                continue
            reading = not (heard or drained) and len(handing) < _RELAY
            ready = _polled(
                (raw, (select.POLLIN if reading else 0) | _out(sending)),
                (
                    plain,
                    (select.POLLIN if len(sending) < _RELAY else 0) | _out(handing),
                ),
            )
            if reading and raw.fileno() in ready:
                more = _received(raw)
                if more:
                    inbound.write(more)
                elif more is not None:
                    inbound.write_eof()
                    drained = True
            if len(sending) < _RELAY and plain.fileno() in ready:
                more = _received(plain)
                if more == b"":
                    break
                if more:
                    tls.write(more)
        _letting_go(raw, tls, outbound, sending)
    except OSError as exc:
        log.debug("a sealed connection was dropped: %s", exc)
    finally:
        plain.close()
        raw.close()


def _letting_go(
    raw: socket.socket, tls: ssl.SSLObject, outbound: ssl.MemoryBIO, sending: bytearray
) -> None:
    """Sends the last of a sealed connection and its close_notify, and lets it go.

    The close_notify is all that is meant by asking for TLS's shutdown here, which in OpenSSL
    goes on to wait for the other end's -- and gives up on the connection if the other end's
    data arrives first. Nothing more is read from it either way, so its answer is not waited
    for; but what arrives is read and dropped for a moment after this end has finished,
    rather than left unread for the kernel to answer with a reset that could cost the other
    end the last of what it was sent.
    """
    with contextlib.suppress(ssl.SSLError):
        tls.unwrap()
    sending += outbound.read()
    ends = time.monotonic() + _ANSWERING
    while sending and time.monotonic() < ends:
        if _polled((raw, select.POLLOUT), timeout=ends - time.monotonic()):
            del sending[: _sent(raw, sending)]
    raw.shutdown(socket.SHUT_WR)
    ends = time.monotonic() + GREETING
    while _polled((raw, select.POLLIN), timeout=ends - time.monotonic()):
        if not _received(raw):
            return


def _out(waiting: bytearray) -> int:
    """Whether a socket is waited on for room to write: when there is something to write."""
    return select.POLLOUT if waiting else 0


def _polled(
    *socks: tuple[socket.socket, int], timeout: float | None = None
) -> set[int]:
    """Waits for any of these sockets to be ready for what each is asked for, or for an end.

    A socket asked for nothing is not waited on at all -- not even for its end, which `poll`
    reports whether it was asked or not and which would otherwise wake this again and again.

    Returns:
      The descriptors of those that are ready, or that ended; none if `timeout` passed.
    """
    poller = select.poll()
    for sock, events in socks:
        if events:
            poller.register(sock, events)
    waiting = None if timeout is None else max(0, int(timeout * 1000))
    return {fd for fd, _ in poller.poll(waiting)}


def _sent(sock: socket.socket, data: bytearray) -> int:
    """How much of `data` a socket that does not block took."""
    try:
        return sock.send(data)
    except BlockingIOError:
        return 0


def _received(sock: socket.socket) -> bytes | None:
    """What a socket that does not block had; `b""` at its end, None for nothing yet."""
    try:
        return sock.recv(_RELAY)
    except BlockingIOError:
        return None


# ------------------------------------------------------------------- the broker's own wire


class _Lines:
    """Reads one JSON object per line off a socket, and not one byte past it.

    A byte at a time, which for four short messages is nothing and buys the one property that
    matters here: when the broker stops speaking this protocol and starts carrying the
    session's own bytes, there is nothing of the session sitting in a buffer this would have
    to hand back.
    """

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def read(self, timeout: float) -> dict[str, Any]:
        """Reads the next object.

        Args:
          timeout: How long to wait for the whole of it.

        Returns:
          What it said.

        Raises:
          OSError: If the connection ends first, or nothing arrives in time.
          ValueError: If what arrived is not one object of JSON.
        """
        said = json.loads(_line(self._sock, timeout))
        if not isinstance(said, dict):
            # A ValueError like every other way a line fails to be one: `json.loads` raises
            # that for a line that is not JSON at all, and a caller sorting malformed input
            # into two kinds by which half of the parse noticed it is a caller written twice.
            raise ValueError("expected one JSON object per line")  # noqa: TRY004
        return said  # pyright: ignore[reportUnknownVariableType]


def _line(sock: socket.socket, timeout: float) -> bytes:
    """One newline-terminated line, read without touching whatever follows it."""
    ends = time.monotonic() + timeout
    held = bytearray()
    while True:
        sock.settimeout(max(0.01, ends - time.monotonic()))
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("the other end went away mid-message")
        if byte == b"\n":
            return bytes(held)
        held += byte
        if len(held) > _LINE:
            raise ValueError("a line of this protocol is longer than it may be")


def _say(sock: socket.socket, said: dict[str, Any]) -> None:
    """Writes one object, whole, with the newline that ends it."""
    sock.sendall(json.dumps(said, separators=(",", ":")).encode() + b"\n")
