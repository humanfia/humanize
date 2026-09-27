"""A workspace's runs, carried between the host holding them and the frontends reaching it.

The runs themselves are :class:`hmz.runtime.Host`'s: the run going, who holds which role, what
is waiting to be said, what every frontend has been told. What is here is only the socket --
one JSON object a frame, a request in and a reply or a message out -- and the process it is
bound in, which a terminal closing cannot end.

Nothing here waits on a frontend. Every socket is written without blocking, what it has not
taken yet is kept against it up to a ceiling, and one that falls further behind than that is
told so and let go of; every request is carried out on a thread of its own connection's,
never on the one carrying everybody's bytes, because starting a flow imports it and an aside
is a turn of an agent.
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
import functools
import io
import json
import os
import queue
import selectors
import socket
import threading
import time
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.daemon import where
from hmz.daemon.proto import (
    CONTROL,
    GONE,
    MESSAGE,
    PROTOCOL,
    Frames,
    asked,
    frame,
    spoken,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.runtime import Host

__all__ = ["Carrier", "Printed", "logged", "serves"]

#: How much is read off a socket at a time, and written to one.
_READ = 1 << 16

#: How much a frontend may let pile up before it is let go of. Nothing here waits on one, so
#: what one that has stopped reading costs is memory, and this is the ceiling on it: a whole
#: replay of a run fits under it.
_BEHIND = 64 << 20

#: How long the loop waits on nothing at all before looking again at whether it is still
#: wanted.
_TICK = 0.5

#: How many rounds in a row may go wrong before the thread carrying them gives up.
_WRONG = 8

#: How long a host nobody has reached yet waits for somebody to: whoever asked for it is a
#: moment away from attaching, and one that never does must not leave a process behind.
_GRACE = 60.0

#: How long a frontend being let go of is given to take what it is still owed.
_FLUSHING = 5.0

#: The longest message a frame of the protocol carries.
_LONGEST = (1 << 22) - 1


@dataclasses.dataclass(slots=True)
class _Reading:
    """One socket on the other end of this daemon, and what has arrived off it so far.

    A socket is on the list from the moment it connects, before it has said what it is for: a
    frontend says so with a `hello` request, and a question about the runs with `CONTROL`. One
    record rather than a dict apiece, so that there is one list to take a socket off rather
    than several to keep in step.

    Attributes:
      one: The socket.
      frames: What has been read off it that is not yet a whole frame.
      joined: Whether it is a frontend reading the runs, rather than one that has not said.
      sending: What it has been sent that it has not taken yet.
      client: The frontend's client id, once it has said hello.
      lengths: How much of what it has not taken is each frame, oldest first, so that one
        let go of mid-frame is still sent whole frames.
      leaving: When it was told to go, or 0 for a socket that has not been.
      asking: What it has asked that has not been carried out yet, in order.
    """

    one: socket.socket
    frames: Frames
    joined: bool = False
    sending: bytearray = dataclasses.field(default_factory=bytearray)
    client: str = ""
    lengths: collections.deque[int] = dataclasses.field(
        default_factory=collections.deque[int]
    )
    leaving: float = 0.0
    asking: queue.SimpleQueue[dict[str, Any] | None] | None = None


def logged(at: Path, about: str) -> None:
    """Writes down what went wrong where nobody was reading a terminal to see it.

    Args:
      at: The daemon's own directory.
      about: What was being done, since whatever is being handled is what raised.
    """
    import sys

    handling = sys.exc_info()[0] is not None
    with (
        contextlib.suppress(OSError),
        (at / where.LOG).open("a", encoding="utf-8") as writing,
    ):
        writing.write(f"{about}\n{traceback.format_exc() if handling else ''}\n")


def _watching(
    selector: selectors.BaseSelector, one: socket.socket | int, *, waiting: bool
) -> None:
    """Says whether one descriptor is worth waking for room to write as well as to read.

    Args:
      selector: What the loop waits on.
      one: The descriptor, or the socket it belongs to.
      waiting: Whether anything is waiting to be written to it.

    Note:
      A descriptor that has gone since the round began is one there is nothing to say about,
      which is what the loop finds out when it closes it.
    """
    wanted = selectors.EVENT_READ | (selectors.EVENT_WRITE if waiting else 0)
    with contextlib.suppress(KeyError, ValueError, OSError):
        if selector.get_key(one).events != wanted:
            selector.modify(one, wanted)


def _quietly(hook: Callable[[], object]) -> None:
    """Runs a hook that must not be able to end what is carrying the run."""
    with contextlib.suppress(Exception):
        hook()


def _listens(at: Path) -> socket.socket:
    """Binds the socket this daemon is reached on, taking away one a daemon that is gone left.

    Called with this workspace's daemon lock already held, so that taking a socket away as
    stale cannot be taking one from a daemon that is coming up beside this.

    Args:
      at: The daemon's own directory.

    Returns:
      The socket, listening.

    Raises:
      OSError: If it cannot be bound.
    """
    path = at / where.SOCKET
    if path.exists():
        # A socket file outlives the process that bound it, and one nothing is listening on
        # is a reader that hangs rather than one that says nothing is running.
        with contextlib.suppress(OSError):
            path.unlink()
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with where.reached(at) as reaching:
            listening.bind(reaching)
        path.chmod(0o600)
        listening.listen(8)
    except OSError:
        listening.close()
        raise
    return listening


def _now() -> str:
    """This moment, to the second, which is how long a daemon's own note has to be true."""
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _written(message: dict[str, Any]) -> bytes:
    """One message as the frame it goes out in."""
    return frame(MESSAGE, json.dumps(message, default=str, ensure_ascii=False).encode())


class Carrier:
    """The socket a host is reached on, and every frontend on the other end of it."""

    def __init__(self, host: Host, listening: socket.socket, at: Path) -> None:
        """Holds the host and the socket it is reached through.

        Args:
          host: The runs being carried.
          listening: The socket frontends arrive on, already bound and listening.
          at: The daemon's own directory, which is where its note and its log are.
        """
        self._host = host
        self._listening = listening
        self._at = at
        self._lock = threading.Lock()
        self._reading: dict[int, _Reading] = {}
        self._letting: list[tuple[socket.socket, bytes]] = []
        self._woken_r, self._woken_w = os.pipe()
        # A wake that finds the pipe full has nothing to add: the loop is already due to wake.
        os.set_blocking(self._woken_w, False)
        self._going = True
        self._ever = False
        self._began = time.monotonic()
        self._closing = 0.0
        self._thread: threading.Thread | None = None
        self._done = threading.Event()

    # -- the loop

    def start(self) -> None:
        """Starts carrying, on a thread of its own."""
        self._thread = threading.Thread(
            target=self._carries, name="humanize-carrier", daemon=True
        )
        self._thread.start()

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for carrying to be over: the host closed, or nothing left to hold it for.

        Args:
          timeout: How long to wait, or None for as long as it takes.

        Returns:
          Whether it is over.
        """
        return self._done.wait(timeout)

    def close(self) -> None:
        """Stops carrying, lets go of every socket, and stops being reachable."""
        self._going = False
        self._wake()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=_FLUSHING + _TICK)
        with contextlib.suppress(OSError):
            self._listening.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (self._at / name).unlink()
        with self._lock:
            fds, self._woken_r, self._woken_w = (self._woken_r, self._woken_w), -1, -1
        for fd in fds:
            with contextlib.suppress(OSError):
                os.close(fd)

    def _wake(self) -> None:
        with self._lock, contextlib.suppress(OSError):
            if self._woken_w >= 0:
                os.write(self._woken_w, b".")

    def _carries(self) -> None:
        selector = selectors.DefaultSelector()
        selector.register(self._listening, selectors.EVENT_READ)
        selector.register(self._woken_r, selectors.EVENT_READ)
        wrong = 0
        try:
            while self._going and wrong < _WRONG:
                try:
                    for key, events in selector.select(_TICK):
                        self._ready(selector, key.fd, events)
                    self._closes(selector)
                    self._watches(selector)
                    self._lives()
                    wrong = 0
                except Exception:  # noqa: BLE001 -- a bad round is not the host over
                    wrong += 1
                    logged(self._at, "the daemon could not carry a round of messages")
        finally:
            with contextlib.suppress(Exception):
                self._closes(selector)
            with self._lock:
                left = list(self._reading.values())
                self._reading.clear()
            for reading in left:
                self._ends(reading)
            selector.close()
            self._done.set()

    def _lives(self) -> None:
        """Says whether there is still something to carry, and lets go once there is not."""
        now = time.monotonic()
        if self._host.closed:
            if not self._closing:
                self._closing = now
            with self._lock:
                # Every frontend is told why it is let go of, which is on its way from the
                # host's own thread for it: owed until it has been said and taken.
                owed = any(
                    one.sending or (one.joined and not one.leaving)
                    for one in self._reading.values()
                )
            if not owed or now - self._closing > _FLUSHING:
                self._going = False
        elif self._host.idle and (self._ever or now - self._began > _GRACE):
            # Nothing running, nothing stopping, nobody reading: a process holding nothing.
            self._host.close()

    def _ready(self, selector: selectors.BaseSelector, fd: int, events: int) -> None:
        if fd == self._woken_r:
            with contextlib.suppress(OSError):
                os.read(self._woken_r, _READ)
            return
        if fd == self._listening.fileno():
            self._arrived(selector)
            return
        if events & selectors.EVENT_WRITE:
            self._sends(fd)
        if events & selectors.EVENT_READ:
            self._heard_from(selector, fd)

    def _arrived(self, selector: selectors.BaseSelector) -> None:
        try:
            one, _ = self._listening.accept()
        except OSError:
            return
        if self._host.closed:
            one.close()
            return
        one.setblocking(False)  # noqa: FBT003 -- what a socket takes, not a flag of ours
        with self._lock:
            self._reading[one.fileno()] = _Reading(one, Frames())
        with contextlib.suppress(ValueError, KeyError, OSError):
            selector.register(one, selectors.EVENT_READ)

    def _watches(self, selector: selectors.BaseSelector) -> None:
        with self._lock:
            held = [(one.one, bool(one.sending)) for one in self._reading.values()]
        for one, waiting in held:
            _watching(selector, one, waiting=waiting)

    # -- what arrives

    def _heard_from(self, selector: selectors.BaseSelector, fd: int) -> None:
        with self._lock:
            reading = self._reading.get(fd)
        if reading is None:
            with contextlib.suppress(KeyError, ValueError, OSError):
                selector.unregister(fd)
            return
        try:
            said = reading.one.recv(_READ)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            said = b""
        if not said:
            self._gone(selector, reading)
            return
        try:
            for kind, payload in reading.frames.feed(said):
                if not self._said(selector, reading, kind, payload):
                    return
        except ValueError:
            # A length no frame has: whatever is on the other end is not speaking this.
            self._gone(selector, reading)

    def _said(
        self,
        selector: selectors.BaseSelector,
        reading: _Reading,
        kind: bytes,
        payload: bytes,
    ) -> bool:
        """Does what one frame asked for. Whether the socket is still to be read."""
        if kind == MESSAGE:
            if reading.asking is None:
                reading.asking = queue.SimpleQueue()
                threading.Thread(
                    target=self._asks,
                    args=(reading, reading.asking),
                    daemon=True,
                    name="humanize-requests",
                ).start()
            reading.asking.put(asked(payload))
            return True
        if kind == CONTROL:
            # Answered off this thread, as every request is, and closed once answered.
            with contextlib.suppress(KeyError, ValueError, OSError):
                selector.unregister(reading.one)
            with self._lock:
                self._reading.pop(reading.one.fileno(), None)
            threading.Thread(
                target=self._answers,
                args=(reading, asked(payload)),
                daemon=True,
                name="humanize-control",
            ).start()
            return False
        # Anything else is a reader speaking another protocol -- an older humanize's terminal,
        # reaching for a run held on a pseudoterminal -- told so rather than left waiting.
        with contextlib.suppress(OSError):
            reading.one.sendall(
                frame(
                    GONE,
                    b"held for frontends by a newer humanize; `hmz` of it reads it",
                )
            )
        self._gone(selector, reading)
        return False

    def _answers(self, reading: _Reading, said: dict[str, Any]) -> None:
        """Answers a question about the runs rather than a frontend reading them."""
        doing = said.get("do")
        answer: dict[str, Any]
        if doing == "status":
            answer = {"ok": True, **where.held(self._at), **self._host.status()}
        elif doing == "detach":
            clients = [one["client"] for one in self._host.status()["clients"]]
            for client in clients:
                self._host.detach(client)
            answer = {"ok": True, "let go": len(clients)}
        elif doing == "stop":
            threading.Thread(
                target=_quietly, args=(self._host.close,), daemon=True
            ).start()
            answer = {"ok": True}
        else:
            answer = {"ok": False, "why": f"no such request: {doing!r}"}
        with contextlib.suppress(OSError):
            reading.one.setblocking(True)  # noqa: FBT003 -- one small answer, then closed
            reading.one.settimeout(_FLUSHING)
            reading.one.sendall(spoken(CONTROL, answer))
        with contextlib.suppress(OSError):
            reading.one.close()

    def _asks(
        self, reading: _Reading, asking: queue.SimpleQueue[dict[str, Any] | None]
    ) -> None:
        """Carries out one frontend's requests in the order it made them."""
        while (said := asking.get()) is not None:
            if said.get("do") == "aside":
                # A turn of an agent, which may take minutes: the frontend's other requests
                # are not held up behind it.
                threading.Thread(
                    target=self._request,
                    args=(reading, said),
                    daemon=True,
                    name="humanize-aside",
                ).start()
            else:
                self._request(reading, said)

    def _request(self, reading: _Reading, said: dict[str, Any]) -> None:
        doing = said.get("do")
        try:
            if doing == "hello":
                answer = self._hello(reading, said)
            elif not reading.client:
                answer = {"ok": False, "why": "a frontend says hello first"}
            else:
                answer = self._host.asked(reading.client, said)
        except Exception as why:  # noqa: BLE001 -- a request that failed is answered as one
            answer = {"ok": False, "why": str(why) or type(why).__name__}
        self._tells(reading, {"type": "reply", "to": said.get("id", ""), **answer})

    def _hello(self, reading: _Reading, said: dict[str, Any]) -> dict[str, Any]:
        if reading.client:
            return {"ok": False, "why": "this frontend has already said hello"}
        client = self._host.attach(
            str(said.get("name") or ""),
            str(said.get("kind") or "sdk"),
            functools.partial(self._told, reading),
            replay=said.get("replay", True) is not False,
        )
        with self._lock:
            # Set where a socket going reads it, so that one of the two sees the other: a
            # socket gone while this was being carried out is let go of here instead.
            reading.client = client
            reading.joined = True
            still = self._reading.get(reading.one.fileno()) is reading
        self._ever = True
        if not still:
            self._host.detach(client)
            return {"ok": False, "why": "the frontend went while it was saying hello"}
        return {"ok": True, "client": client}

    # -- what goes out

    def _told(self, reading: _Reading, message: dict[str, Any]) -> None:
        """Puts one message the host said on its way to one frontend, without waiting."""
        written = _written(message)
        if len(written) > _LONGEST:
            logged(self._at, f"a {message.get('type')} message was too long to carry")
            return
        behind = False
        with self._lock:
            if (
                self._reading.get(reading.one.fileno()) is not reading
                or reading.leaving
            ):
                return
            self._queues(reading, written)
            if len(reading.sending) > _BEHIND:
                behind = True
                self._behind(reading)
            elif message.get("type") == "gone":
                reading.leaving = time.monotonic()
        self._wake()
        if behind and reading.client:
            self._host.detach(reading.client)

    def _tells(self, reading: _Reading, message: dict[str, Any]) -> None:
        """Puts one reply on its way to the frontend that asked, whatever it is owed besides."""
        with self._lock:
            if self._reading.get(reading.one.fileno()) is not reading:
                return
            self._queues(reading, _written(message))
        self._wake()

    @staticmethod
    def _queues(reading: _Reading, written: bytes) -> None:
        reading.sending += written
        reading.lengths.append(len(written))

    def _behind(self, reading: _Reading) -> None:
        """Lets go of a frontend too far behind, telling it so after the frame it is in."""
        head = reading.lengths[0] if reading.lengths else 0
        del reading.sending[head:]
        reading.lengths = collections.deque([head] if head else [])
        self._queues(
            reading,
            _written({"type": "gone", "why": "too far behind; attach again"}),
        )
        reading.leaving = time.monotonic()

    def _sends(self, fd: int) -> None:
        """Writes what one frontend has waiting, as much of it as it will take now.

        Under the lock, which a send that never waits holds for no time at all: what is
        waiting is also what letting a frontend go cuts down, and the two must not interleave.
        """
        broken: _Reading | None = None
        with self._lock:
            reading = self._reading.get(fd)
            while reading is not None and reading.sending:
                try:
                    written = reading.one.send(bytes(reading.sending[: _READ * 16]))
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    broken = reading
                    break
                del reading.sending[:written]
                while written and reading.lengths:
                    if written >= reading.lengths[0]:
                        written -= reading.lengths.popleft()
                    else:
                        reading.lengths[0] -= written
                        written = 0
        if broken is not None:
            self._drops(broken)

    # -- letting go

    def _drops(self, reading: _Reading) -> None:
        """Lets go of one socket that has gone, which the round closes."""
        with self._lock:
            if self._reading.pop(reading.one.fileno(), None) is None:
                return
            self._letting.append((reading.one, b""))
        self._ends(reading, closing=False)
        self._wake()

    def _gone(self, selector: selectors.BaseSelector, reading: _Reading) -> None:
        """Takes one socket off the list and closes it, now."""
        with contextlib.suppress(KeyError, ValueError, OSError):
            selector.unregister(reading.one)
        with self._lock:
            self._reading.pop(reading.one.fileno(), None)
        self._ends(reading)

    def _ends(self, reading: _Reading, *, closing: bool = True) -> None:
        """What a socket going ends: its frontend, and its requests."""
        if reading.asking is not None:
            reading.asking.put(None)
        if reading.client:
            self._host.detach(reading.client)
        if closing:
            with contextlib.suppress(OSError):
                reading.one.close()

    def _closes(self, selector: selectors.BaseSelector) -> None:
        """Closes whatever has been let go of, and whatever has taken all it was owed."""
        now = time.monotonic()
        with self._lock:
            going, self._letting = self._letting, []
            done = [
                one
                for one in self._reading.values()
                if one.leaving and (not one.sending or now - one.leaving > _FLUSHING)
            ]
            for one in done:
                self._reading.pop(one.one.fileno(), None)
        for one, last in going:
            with contextlib.suppress(KeyError, ValueError, OSError):
                selector.unregister(one)
            if last:
                with contextlib.suppress(OSError):
                    one.sendall(last)
            with contextlib.suppress(OSError):
                one.close()
        for reading in done:
            with contextlib.suppress(KeyError, ValueError, OSError):
                selector.unregister(reading.one)
            self._ends(reading)


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


def serves(host: Host, at: Path, telling: int | None = None) -> None:
    """Holds a workspace's runs on a socket of their own, until nothing is left to hold.

    Args:
      host: The runs.
      at: The daemon's own directory, which is made here.
      telling: A descriptor to say on that it is listening, and then close, or None.

    Raises:
      OSError: If a daemon of this workspace is already running, or the socket cannot be
        bound -- the one failure whoever asked for a daemon has to hear about.
    """
    at.mkdir(parents=True, exist_ok=True)
    # Taken before anything is looked at: two started in the same second would both find
    # nothing here, and one of them would take the other's socket away as stale.
    holding = where.holds(at)
    try:
        listening = _listens(at)
        where.wrote(
            at,
            {
                "pid": os.getpid(),
                "workspace": str(Path.cwd()),
                "started": _now(),
                "kind": "host",
                "protocol": PROTOCOL,
            },
        )
        if telling is not None:
            with contextlib.suppress(OSError):
                os.write(telling, b"listening\n")
                os.close(telling)
        carrier = Carrier(host, listening, at)
        carrier.start()
        try:
            carrier.wait()
        finally:
            host.close()
            carrier.close()
    finally:
        with contextlib.suppress(OSError):
            os.close(holding)
