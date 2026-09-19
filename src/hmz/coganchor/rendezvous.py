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

Which of the three a session got is not a thing the session is told. The channel is a socket
either way, the protocol above it is the same protocol, and a flow that would have to behave
differently for a relayed session is a flow that would have to know something no end of a
connection can honestly report.

The whole of it is IPv4 and deliberately so: a hole is punched from one port to one address,
and a candidate the other half cannot open a matching socket for is a candidate that only
spends the window. A machine reachable only over IPv6 relays, which is the answer this already
has for every other unreachable pair.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import queue
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, cast

__all__ = [
    "ANCHOR",
    "SERVE",
    "Broker",
    "Meeting",
    "dial",
    "shared",
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

#: How long a half waits on the broker's own answers, which are sent as soon as it has them.
_ANSWERING = 30.0

#: How many tickets one broker will hold at once. A cap rather than a policy: pairing is by a
#: secret nobody can guess, so the only thing a stranger can do here is ask for room.
_TICKETS = 4096

#: How many pairs of machines a broker remembers having failed to introduce, and how often it
#: tries them again anyway. Two machines with no route between them do not grow one between
#: one session and the next, so a deployment that relays spends the whole punching window per
#: session for an answer it already has -- which at a hundred sessions is several minutes of
#: nothing happening. So the answer is kept, and every so often disbelieved: a firewall rule
#: *is* the kind of thing that changes, and a broker certain of an old one would keep carrying
#: sessions that could now go straight across.
_HOPELESS = 1024
_DISBELIEVING = 16

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


def dial(meeting: Meeting, role: str, *, timeout: float = PAIRING) -> socket.socket:
    """Meets the other half of a session and answers with the socket joining the two.

    The same call on both machines, differing only in which half is calling it. It returns
    when there is a connection the other half is holding the other end of -- punched through
    to that machine where the two could be introduced, carried by the broker where they could
    not -- and what it returns is a socket either way.

    Args:
      meeting: Which broker, and under what ticket.
      role: :data:`ANCHOR` or :data:`SERVE`, whichever half this is.
      timeout: How long to wait at the broker for the other half to arrive.

    Returns:
      The socket carrying the session. Blocking, with no timeout set, ready for
      :meth:`~hmz.coganchor.proto.Channel.from_socket`.

    Raises:
      ValueError: If `role` is not one of the two.
      OSError: If the broker cannot be reached, the other half never arrives, or the two
        could be neither introduced nor carried.
    """
    if role not in ROLES:
        raise ValueError(f"unsupported role {role!r}; expected {ANCHOR} or {SERVE}")
    home = _outward()
    ear: socket.socket | None = None
    punched: socket.socket | None = None
    try:
        home.settimeout(timeout)
        home.connect((meeting.host, meeting.port))
        port = int(home.getsockname()[1])
        # The same port the broker was dialled from, so that whatever a NAT made of this
        # connection is the mapping the other half is about to be sent at. A machine whose
        # kernel will not lend the port twice still punches outward and is still reachable at
        # whatever it is given; it simply has no address of its own worth advertising.
        ear = _listening(port)
        lines = _Lines(home)
        _say(home, {"ticket": meeting.ticket, "role": role, "at": _mine(home, port)})
        seen = lines.read(timeout).get("seen")
        log.debug("the broker sees this half at %s", seen)
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
        punched = _punch(
            ear, port, said["peer"], meeting.ticket, role, float(said.get("punch", 0.0))
        )
        _say(home, {"direct": punched is not None})
        # The broker's word rather than this half's: one end can have a socket the other end
        # never learned it had, and two halves disagreeing about which pipe the session is on
        # is a session that hangs with both of them certain they are right.
        agreed = lines.read(_ANSWERING).get("go")
        if agreed == "direct" and punched is not None:
            log.debug("joined %s directly", meeting.ticket[:8])
            home.close()
            return _settled(punched)
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
        return held  # noqa: TRY300
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
    ) -> None:
        """Prepares a broker, without listening yet.

        Args:
          host: The address to listen on. Every interface by default: the halves being
            introduced are on other machines, which is the only reason this exists.
          port: The port, or 0 to be given one.
          patience: How long one half waits here for the other.
          punching: How long the two are given to reach each other before being carried.
        """
        self._host = host
        self._port = port
        self._patience = patience
        self._punching = punching
        self._lock = threading.Lock()
        self._meetings: dict[str, _Pair] = {}
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
            listener.listen(64)
        except OSError:
            listener.close()
            raise
        self._listener = listener
        self._thread = threading.Thread(
            target=self._accept, name="rendezvous", daemon=True
        )
        self._thread.start()
        return self.address

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
        lines = _Lines(half)
        pair: _Pair | None = None
        role = ""
        try:
            hello = lines.read(_ANSWERING)
            name, role = str(hello.get("ticket", "")), str(hello.get("role", ""))
            if not name or role not in ROLES:
                _say(half, {"go": "no", "why": "say a ticket and a role"})
                return
            # Its own address as the world has it, which is the one fact about a machine
            # behind a NAT that only somebody outside it can supply.
            _say(half, {"seen": [whence[0], whence[1]]})
            mine = [*_pairs(hello.get("at")), (whence[0], whence[1])]
            pair = self._join(name, role, half, mine)
            if pair is None:
                _say(half, {"go": "no", "why": "too many meetings are open here"})
                return
            other = pair.await_other(role, self._patience)
            if other is None:
                _say(half, {"go": "no", "why": "the other half never arrived"})
                return
            between = pair.between()
            punching = self._punching if self._worth(between) else 0.0
            _say(half, {"peer": other, "punch": punching})
            direct = bool(lines.read(punching + _ANSWERING).get("direct"))
            joined = pair.settle(role, direct=direct, patience=_ANSWERING)
            _say(half, {"go": "direct" if joined else "relay"})
            if role == ANCHOR:
                self._learn(between, worked=joined)
            if not joined:
                if role == ANCHOR:
                    self._carried += 1
                pair.carry(role)
        except (OSError, ValueError) as exc:
            log.debug("a half of %s left: %s", role or "a meeting", exc)
        finally:
            if pair is not None:
                self._forget(pair, role)
            with contextlib.suppress(OSError):
                half.close()

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
        # Nought is never here -- a pair only arrives once it has failed -- so what the
        # modulus answers is the attempt *after* the sixteenth failure, and every sixteenth
        # failure after that one.
        return failed == 0 or failed % _DISBELIEVING == 0

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
        self, name: str, role: str, half: socket.socket, mine: list[tuple[str, int]]
    ) -> _Pair | None:
        """Puts one half into its meeting, making the meeting if it is the first there."""
        with self._lock:
            pair = self._meetings.get(name)
            if pair is None:
                if len(self._meetings) >= _TICKETS:
                    return None
                pair = self._meetings[name] = _Pair(name)
        pair.arrive(role, half, mine)
        return pair

    def _forget(self, pair: _Pair, role: str) -> None:
        """Takes a meeting away once the last half of it has gone."""
        if pair.leave(role):
            with self._lock:
                if self._meetings.get(pair.name) is pair:
                    del self._meetings[pair.name]


@dataclass
class _Pair:
    """One meeting: the two halves of it, and everything either is waiting on the other for."""

    name: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    halves: dict[str, socket.socket] = field(default_factory=dict[str, socket.socket])
    theirs: dict[str, list[tuple[str, int]]] = field(
        default_factory=dict[str, list[tuple[str, int]]]
    )
    verdicts: dict[str, bool] = field(default_factory=dict[str, bool])
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
    #: Set once the bytes have finished flowing, for whichever thread is not carrying them.
    done: threading.Event = field(default_factory=threading.Event)

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
        weaker of the two, for both of them.
        """
        with self.lock:
            self.verdicts[role] = direct
        self.answered[role].set()
        if not self.answered[_OPPOSITE[role]].wait(patience):
            return False
        with self.lock:
            return all(self.verdicts.get(name, False) for name in ROLES)

    def carry(self, role: str) -> None:
        """Moves the bytes between the two, for a pair that could not be introduced.

        One of the two threads does the carrying and the other waits for it, so that neither
        socket is closed from under the splice by the half that stopped having anything to do.
        """
        if role != ANCHOR:
            self.done.wait(timeout=None)
            return
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
    """
    source.settimeout(None)
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


# ------------------------------------------------------------------------ punching a hole


def _punch(
    ear: socket.socket | None,
    port: int,
    candidates: list[Any],
    name: str,
    role: str,
    seconds: float,
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

    Returns:
      The socket joining the two, or None if the window closed with nothing through it.
    """
    where_to = _pairs(candidates)
    if not where_to and ear is None:
        return None
    deadline = time.monotonic() + seconds
    won: queue.Queue[socket.socket] = queue.Queue()
    claimed = threading.Event()
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=_knocking,
            args=(where, port, name, role, won, claimed, stop, deadline),
            daemon=True,
        )
        for where in where_to
    ]
    if ear is not None:
        threads.append(
            threading.Thread(
                target=_answering,
                args=(ear, name, role, won, claimed, stop, deadline),
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
    won: queue.Queue[socket.socket],
    claimed: threading.Event,
    stop: threading.Event,
    deadline: float,
) -> None:
    """Keeps opening outward at one candidate until something answers or time runs out."""
    while not stop.is_set() and time.monotonic() < deadline:
        knock = _outward()
        try:
            knock.bind(("", port))
            knock.settimeout(max(0.2, min(1.0, deadline - time.monotonic())))
            knock.connect(where)
        except OSError:
            knock.close()
            # A beat before the next one: a refused connection is instant, and a tight loop
            # on it would spend the window on syscalls rather than on giving the other half
            # time to open its own side.
            stop.wait(0.05)
            continue
        _greet(knock, name, role, won, claimed)
        return


def _answering(
    ear: socket.socket,
    name: str,
    role: str,
    won: queue.Queue[socket.socket],
    claimed: threading.Event,
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
        threading.Thread(
            target=_greet,
            args=(arrived, name, role, won, claimed),
            daemon=True,
        ).start()


def _greet(
    punched: socket.socket,
    name: str,
    role: str,
    won: queue.Queue[socket.socket],
    claimed: threading.Event,
) -> None:
    """Proves a connection is the other half of this session, and settles who keeps it.

    Both ends say the same thing first -- this protocol, the ticket's digest, which half they
    are -- so a connection to anything else, and a connection to one's own listener, is over
    before either end has told it anything. What follows decides between the several sockets
    that may have got through at once: the anchoring half offers each one it has and the
    serving half accepts exactly one, which is an agreement neither can reach alone.
    """
    kept = False
    try:
        punched.settimeout(GREETING)
        proof = hashlib.sha256(name.encode()).hexdigest().encode()
        punched.sendall(b" ".join((_MAGIC, proof, role.encode())) + b"\n")
        said = _line(punched, GREETING).split()
        if said[:2] != [_MAGIC, proof] or said[2:3] != [_OPPOSITE[role].encode()]:
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
            if claimed.is_set():
                return
            claimed.set()
            punched.sendall(_OK + b"\n")
        kept = True
        won.put(punched)
    except (OSError, ValueError, IndexError):
        return
    finally:
        if not kept:
            # Closed where it lost rather than gathered up afterwards: this may be running in
            # a thread nothing is waiting on, and a socket left for somebody else to sweep is
            # one nobody sweeps.
            punched.close()


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


def _listening(port: int) -> socket.socket | None:
    """The socket the peer's punch arrives on, or None where the port cannot be shared."""
    ear = _outward()
    try:
        ear.bind(("", port))
        ear.listen(8)
    except OSError as exc:
        log.debug("this half cannot listen on %s as well: %s", port, exc)
        ear.close()
        return None
    return ear


def _settled(held: socket.socket) -> socket.socket:
    """Hands a socket on as the session wants it: blocking, with nothing timing it out."""
    held.settimeout(None)
    held.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return held


def _mine(home: socket.socket, port: int) -> list[tuple[str, int]]:
    """Where this half says it can be reached, before the broker adds what it saw.

    The address this machine reached the broker from comes first, being the one it would be
    reached back at by anything on the same network; its other names follow, for the case
    where the broker is somewhere else entirely and the two halves are neighbours.
    """
    addresses = [str(home.getsockname()[0])]
    with contextlib.suppress(OSError):
        for found in socket.getaddrinfo(
            socket.gethostname(), port, socket.AF_INET, socket.SOCK_STREAM
        ):
            address = str(found[4][0])
            if address not in addresses:
                addresses.append(address)
    return [(address, port) for address in addresses]


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
