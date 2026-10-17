"""Sealed meetings: two halves joined through a real broker on loopback over pinned TLS.

The broker and the anchoring half hold a key and the certificate made with it, as this machine
does; the serving half holds the certificate alone, as a swarm task is handed it. What is
checked is that a session gets through both ways -- punched and carried -- with nothing of it,
nor any ticket, crossing in the clear; and that whoever presents another certificate, or none,
or speaks no TLS at all, is let in nowhere and told nothing.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import hmz
from hmz.coganchor import AnchorConfig, anchor, transport
from hmz.coganchor.providers import redirect
from hmz.coganchor.remote import RemoteClient
from hmz.coganchor.rendezvous import (
    ANCHOR,
    CERTIFICATE,
    SERVE,
    Broker,
    Meeting,
    dial,
    meet,
    standing,
    ticket,
)
from tests.integration.doubles_anchor import stopped

if TYPE_CHECKING:
    from collections.abc import Iterator

PATIENCE = 20.0

#: What the serving half left at a booked meeting proves itself with, here.
KEY = "k" * 32

#: What each session says, which must never be seen on the wire.
MARKER = b"MARKER-the-session-itself-0123456789"

#: The serving half as a swarm task runs it, from this checkout.
SERVING_HALF = [sys.executable, "-Pm", "hmz", "internal", "anchor", "serve"]


def certified(at: Path) -> Path:
    """A directory holding a fresh key and the self-signed certificate made with it."""
    at.mkdir(mode=0o700)
    subprocess.run(
        [
            *("openssl", "req", "-x509", "-nodes", "-days", "1"),
            *("-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1"),
            *("-subj", "/CN=test", "-keyout", str(at / "key.pem")),
            *("-out", str(at / CERTIFICATE)),
        ],
        capture_output=True,
        check=True,
    )
    return at


def handed(sealed: Path, at: Path) -> Path:
    """What a task is handed of a sealed broker: the certificate, and not the key."""
    at.mkdir()
    shutil.copy(sealed / CERTIFICATE, at / CERTIFICATE)
    return at


@pytest.fixture
def sealed(tmp_path: Path) -> Path:
    return certified(tmp_path / "broker")


@pytest.fixture
def task(sealed: Path, tmp_path: Path) -> Path:
    return handed(sealed, tmp_path / "task")


def _booked(sealed: Path, *, punching: float) -> Iterator[Broker]:
    made = Broker("127.0.0.1", 0, punching=punching, booked=True, tls=str(sealed))
    made.start()
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def punching(sealed: Path) -> Iterator[Broker]:
    """A sealed broker that gives the two halves a window to reach each other in."""
    yield from _booked(sealed, punching=2.0)


@pytest.fixture
def carrying(sealed: Path) -> Iterator[Broker]:
    """A sealed broker with no window at all, which carries every pair it is given."""
    yield from _booked(sealed, punching=0.0)


def _standing(
    at: Meeting, key: str = KEY
) -> tuple[threading.Thread, dict[str, object]]:
    """A serving half waiting at a booked meeting, in a thread, and what it came to."""
    came: dict[str, object] = {}

    def wait() -> None:
        try:
            came["met"], came["asked"] = meet(at, SERVE, key=key, timeout=PATIENCE)
        except OSError as exc:
            came["failed"] = exc

    waiting = threading.Thread(target=wait)
    waiting.start()
    return waiting, came


def joined(
    broker: Broker,
    sealed: Path,
    task: Path,
    *,
    tickets: tuple[str, str] | None = None,
    via: tuple[str, int] | None = None,
) -> tuple[socket.socket, socket.socket]:
    """An anchoring half and the serving half it met, at a meeting booked with `broker`.

    `tickets` are the meeting's, for one booked already; `via` is where the serving half
    dials the broker instead of where it is, for a hop that watches what crosses.
    """
    serving, anchoring = tickets or broker.stand()
    host, port = broker.address
    waiting, came = _standing(Meeting(serving, *(via or (host, port)), str(task)))
    anchored = dial(
        Meeting(anchoring, host, port, str(sealed)),
        ANCHOR,
        timeout=PATIENCE,
        asks=["/w:/real"],
    )
    waiting.join(PATIENCE)
    served = came.get("met")
    assert isinstance(served, socket.socket), came
    assert came["asked"] == ("/w:/real",)
    for one in (anchored, served):
        one.settimeout(PATIENCE)
    return anchored, served


def received(sock: socket.socket) -> bytes:
    """Everything a socket is sent until its other end is done."""
    got = bytearray()
    while chunk := sock.recv(1 << 16):
        got += chunk
    return bytes(got)


def received_exactly(sock: socket.socket, size: int) -> bytes:
    got = bytearray()
    while len(got) < size and (chunk := sock.recv(min(1 << 16, size - len(got)))):
        got += chunk
    return bytes(got)


def test_a_sealed_meeting_is_joined_and_talks_both_ways(
    punching: Broker, sealed: Path, task: Path
) -> None:
    anchored, served = joined(punching, sealed, task)
    try:
        anchored.sendall(MARKER)
        assert served.recv(64) == MARKER
        served.sendall(b"from the task")
        assert anchored.recv(64) == b"from the task"
        # Both at once, each far more than any buffer between them holds: a session is a
        # file going one way while output comes back the other.
        ways = {one: os.urandom(4 << 20) for one in (anchored, served)}
        got: dict[socket.socket, bytes] = {}

        def read(one: socket.socket) -> None:
            got[one] = received_exactly(one, 4 << 20)

        sending = [
            threading.Thread(target=one.sendall, args=(ways[one],)) for one in ways
        ]
        reading = [threading.Thread(target=read, args=(one,)) for one in ways]
        for thread in sending + reading:
            thread.start()
        for thread in sending + reading:
            thread.join(PATIENCE)
        assert got == {anchored: ways[served], served: ways[anchored]}
    finally:
        anchored.close()
        served.close()
    if sys.platform == "linux":
        # Linux lends one port to the dialling socket and the listener both, so on loopback
        # the two always reach each other: this session was punched, and TLS held it there.
        assert punching.carried == 0


def test_a_sealed_meeting_given_no_window_is_carried_whole_and_ended(
    carrying: Broker, sealed: Path, task: Path
) -> None:
    payload = bytes(range(256)) * 4096  # a megabyte: many records, many relay frames
    anchored, served = joined(carrying, sealed, task)
    try:
        sender = threading.Thread(target=anchored.sendall, args=(payload,))
        sender.start()
        got = b""
        while len(got) < len(payload) and (chunk := served.recv(1 << 16)):
            got += chunk
        sender.join(PATIENCE)
        served.sendall(payload)
        assert received_exactly(anchored, len(payload)) == payload
        # A half that is done is heard to be done, after all it sent, through both sealed
        # connections and the splice between them.
        served.sendall(b"last")
        served.close()
        assert received(anchored) == b"last"
    finally:
        anchored.close()
        served.close()
    assert got == payload
    assert carrying.carried == 1


class Watching:
    """A hop between a half and the broker, keeping a copy of every byte either way."""

    def __init__(self, to: tuple[str, int]) -> None:
        self.to = to
        self.seen = bytearray()
        self._lock = threading.Lock()
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.address: tuple[str, int] = self._listener.getsockname()[:2]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                one, _ = self._listener.accept()
            except OSError:
                return
            other = socket.create_connection(self.to)
            for source, sink in ((one, other), (other, one)):
                threading.Thread(
                    target=self._pour, args=(source, sink), daemon=True
                ).start()

    def _pour(self, source: socket.socket, sink: socket.socket) -> None:
        with contextlib.suppress(OSError):
            while chunk := source.recv(1 << 16):
                with self._lock:
                    self.seen += chunk
                sink.sendall(chunk)
        with contextlib.suppress(OSError):
            sink.shutdown(socket.SHUT_WR)

    def close(self) -> None:
        self._listener.close()


def test_nothing_of_a_sealed_meeting_crosses_in_the_clear(
    carrying: Broker, sealed: Path, task: Path
) -> None:
    watching = Watching(carrying.address)
    serving, anchoring = carrying.stand()
    try:
        anchored, served = joined(
            carrying, sealed, task, tickets=(serving, anchoring), via=watching.address
        )
        anchored.sendall(MARKER)
        assert received_exactly(served, len(MARKER)) == MARKER
        served.sendall(MARKER[::-1])
        assert received_exactly(anchored, len(MARKER)) == MARKER[::-1]
        anchored.close()
        served.close()
    finally:
        watching.close()
    seen = bytes(watching.seen)
    # Everything the task's half and the broker said to each other went through the hop --
    # its ticket and key, the anchor's asks, the session both ways -- and none of it is there.
    assert seen[:1] == b"\x16"  # a TLS handshake record, first thing
    for secret in (serving, anchoring, KEY, "/w:/real", '"ticket"'):
        assert secret.encode() not in seen
    assert MARKER not in seen
    assert MARKER[::-1] not in seen


def test_a_half_tells_a_broker_presenting_another_certificate_nothing(
    tmp_path: Path, task: Path
) -> None:
    impostor = certified(tmp_path / "impostor")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(impostor / CERTIFICATE, impostor / "key.pem")
    heard = bytearray()
    listener = socket.create_server(("127.0.0.1", 0))

    def impersonate() -> None:
        one, _ = listener.accept()
        with (
            contextlib.suppress(OSError),
            context.wrap_socket(one, server_side=True) as tls,
        ):
            tls.settimeout(PATIENCE)
            while chunk := tls.recv(1 << 16):
                heard.extend(chunk)

    answering = threading.Thread(target=impersonate)
    answering.start()
    with pytest.raises(OSError, match="certificate other than this meeting's"):
        meet(
            Meeting(ticket(), "127.0.0.1", listener.getsockname()[1], str(task)),
            SERVE,
            key=KEY,
            timeout=PATIENCE,
        )
    answering.join(PATIENCE)
    listener.close()
    # Refused before a word: neither the ticket nor the key was said to it.
    assert heard == b""


def test_a_half_pinned_to_another_certificate_refuses_the_broker(
    punching: Broker, sealed: Path, task: Path, tmp_path: Path
) -> None:
    other = handed(certified(tmp_path / "other"), tmp_path / "pinned-elsewhere")
    serving, anchoring = punching.stand()
    host, port = punching.address
    with pytest.raises(OSError, match="certificate other than this meeting's"):
        meet(Meeting(serving, host, port, str(other)), SERVE, key="x" * 32)
    # Nothing was said to the broker, so the task's own half is still the first to come with
    # its ticket, and is the one met.
    anchored, served = joined(punching, sealed, task, tickets=(serving, anchoring))
    anchored.close()
    served.close()


def test_a_sealed_broker_answers_nothing_said_in_the_clear(
    punching: Broker, sealed: Path, task: Path
) -> None:
    serving, anchoring = punching.stand()
    host, port = punching.address
    with socket.create_connection((host, port), timeout=PATIENCE) as clear:
        hello: dict[str, object] = {"ticket": serving, "role": SERVE, "key": "x" * 32}
        clear.sendall(json.dumps(hello).encode() + b"\n")
        answer = bytearray()
        with contextlib.suppress(OSError):
            while chunk := clear.recv(1 << 16):
                answer += chunk
    # A TLS alert at most, and then the end: never a line of the broker's.
    assert b"{" not in answer
    assert b"seen" not in answer
    # A half that does not seal its meeting gets no further.
    with pytest.raises(OSError, match=r"."):
        dial(Meeting(anchoring, host, port), ANCHOR, timeout=5)
    # And neither claimed the meeting: the task's own half is met there as before.
    anchored, served = joined(punching, sealed, task, tickets=(serving, anchoring))
    anchored.close()
    served.close()


def test_a_sealed_meetings_tickets_let_in_their_own_half_and_nobody_else(
    punching: Broker, sealed: Path, task: Path
) -> None:
    serving, anchoring = punching.stand()
    host, port = punching.address
    anchored, served = joined(punching, sealed, task, tickets=(serving, anchoring))
    anchored.close()
    served.close()
    refused = "no meeting here lets that half in"
    # What anything running in the task may read: its ticket, and the certificate.
    seen_there = Meeting(serving, host, port, str(task))
    with pytest.raises(OSError, match=refused):
        dial(seen_there, ANCHOR, timeout=PATIENCE)
    with pytest.raises(OSError, match=refused):
        dial(seen_there, SERVE, timeout=PATIENCE)
    with pytest.raises(OSError, match=refused):
        meet(seen_there, SERVE, key="x" * 32, timeout=PATIENCE)
    with pytest.raises(OSError, match=refused):
        dial(Meeting(anchoring, host, port, str(task)), SERVE, timeout=PATIENCE)
    with pytest.raises(OSError, match=refused):
        dial(Meeting(ticket(), host, port, str(task)), ANCHOR, timeout=PATIENCE)


def test_whoever_reaches_a_punching_anchor_cannot_be_joined_by_saying_its_words_back(
    sealed: Path,
) -> None:
    proof = "p" * 32
    words: dict[str, bytes] = {}
    told_go = threading.Event()

    # Somebody on the network, at the address the anchoring half is told to punch to: it
    # takes the TLS the anchor serves, hears the anchor's greeting, and says it back as the
    # serving half would -- which is all a reflection needs where both say the same thing.
    stranger = socket.create_server(("127.0.0.1", 0))
    looking = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    looking.check_hostname = False
    looking.verify_mode = ssl.CERT_NONE

    def reflect() -> None:
        stranger.settimeout(PATIENCE)
        with contextlib.suppress(OSError):
            one, _ = stranger.accept()
            with looking.wrap_socket(one) as tls:
                tls.settimeout(PATIENCE)
                said = tls.recv(4096)
                words["anchor"] = said
                magic, digest, _ = said.split()
                tls.sendall(b" ".join((magic, digest, SERVE.encode())) + b"\n")
                if tls.recv(16).startswith(b"GO"):
                    told_go.set()

    # And a broker that sends the anchoring half there, as a broker sends it to its peer.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(sealed / CERTIFICATE, sealed / "key.pem")
    broker = socket.create_server(("127.0.0.1", 0))

    def introduce() -> None:
        one, whence = broker.accept()
        with context.wrap_socket(one, server_side=True) as tls:
            lines = tls.makefile("rwb")
            json.loads(lines.readline())
            for said in (
                {"seen": list(whence)},
                {
                    "peer": [list(stranger.getsockname()[:2])],
                    "punch": 3.0,
                    "proof": proof,
                },
            ):
                lines.write(json.dumps(said).encode() + b"\n")
                lines.flush()
            words["direct"] = lines.readline()
            lines.write(b'{"go": "no"}\n')
            lines.flush()

    threads = [threading.Thread(target=one) for one in (reflect, introduce)]
    for one in threads:
        one.start()
    with pytest.raises(OSError, match="will not join"):
        dial(
            Meeting(ticket(), "127.0.0.1", broker.getsockname()[1], str(sealed)),
            ANCHOR,
            timeout=PATIENCE,
        )
    for one in threads:
        one.join(PATIENCE)
    stranger.close()
    broker.close()
    # It was reached, over TLS, and heard a proof bound to the anchoring half -- which is no
    # use said back: the anchor offered it nothing, and punched through to nobody.
    expected = hmac.new(proof.encode(), ANCHOR.encode(), hashlib.sha256).hexdigest()
    assert words["anchor"].split()[1:] == [expected.encode(), ANCHOR.encode()]
    assert not told_go.is_set()
    assert json.loads(words["direct"]) == {"direct": False}


#: What a process standing a broker for booked meetings says of the key it was made, as it is.
_MINTED = """
import json, os, stat
from pathlib import Path
import hmz
from hmz.coganchor.rendezvous import CERTIFICATE, standing
at = Path(standing("127.0.0.1")[0].tls)
print(json.dumps({
    "machine": str(hmz.machine()),
    "at": str(at),
    "pid": os.getpid(),
    "mode": stat.S_IMODE(at.stat().st_mode),
    "key": stat.S_IMODE((at / "key.pem").stat().st_mode),
    "uid": at.stat().st_uid,
    "certificate": (at / CERTIFICATE).read_text(),
}))
"""


def test_the_broker_for_booked_meetings_is_sealed_with_a_key_of_this_machines_alone() -> (
    None
):
    # Read in a process of its own: a broker is one per process and address, and this
    # process may hold one an earlier test stood, under that test's directory.
    said = subprocess.run(
        [sys.executable, "-P", "-c", _MINTED],
        capture_output=True,
        text=True,
        check=True,
        timeout=PATIENCE,
    )
    minted = json.loads(said.stdout)
    at = Path(minted["at"])
    assert at.parent == Path(minted["machine"]) == hmz.machine()
    # Named for its process, for the next one to remove should that one be killed.
    assert at.name.startswith(f"rendezvous-{minted['pid']}-")
    assert minted["mode"] == 0o700
    assert minted["key"] == 0o600
    assert minted["certificate"].startswith("-----BEGIN CERTIFICATE-----")
    assert minted["uid"] == os.getuid()
    # And it is a broker that meets nobody in the clear.
    broker, port = standing("127.0.0.1")
    serving, anchoring = broker.stand()
    with pytest.raises(OSError, match=r"."):
        dial(Meeting(anchoring, "127.0.0.1", port), ANCHOR, timeout=5)
    broker.withdraw(serving)


@pytest.mark.parametrize("window", [2.0, 0.0], ids=["punched", "carried"])
def test_a_serving_half_as_a_task_runs_it_serves_sealed_sessions_at_once(
    sealed: Path, task: Path, tmp_path: Path, window: float
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    for name in ("a.txt", "b.txt"):
        (workspace / name).write_text(name)
    broker = Broker("127.0.0.1", 0, punching=window, booked=True, tls=str(sealed))
    host, port = broker.start()
    serving, anchoring = broker.stand()
    peer = tmp_path / "peer"
    peer.write_text(f"{Meeting(serving, host, port, str(task))}\n")
    process = subprocess.Popen(
        [*SERVING_HALF, "--peer-file", str(peer), "--export", "/"],
        stdin=subprocess.DEVNULL,
    )
    target = f"peer://{Meeting(anchoring, host, port, str(sealed))}"
    config = AnchorConfig(target=target, workspace=str(workspace))
    said: list[int] = []

    def one() -> None:
        said.append(anchor.check(config)["entries"])

    payload = os.urandom(3 << 20)
    back = io.BytesIO()
    try:
        one()
        many = [threading.Thread(target=one) for _ in range(4)]
        for each in many:
            each.start()
        for each in many:
            each.join(timeout=120)
        # And a file each way, bigger than any one record or relay frame.
        link = transport.connect(transport.Target.parse(target), ["/"])
        client = RemoteClient(link.channel)
        try:
            client.start()
            client.write_file(str(workspace / "big"), io.BytesIO(payload))
            client.read_file(str(workspace / "big"), back)
        finally:
            client.close()
            link.close()
    finally:
        stopped(process)
        broker.close()
    assert said == [2] * 5
    assert (workspace / "big").read_bytes() == payload
    assert back.getvalue() == payload
    if not window:
        assert broker.carried == 6
    elif sys.platform == "linux":
        assert broker.carried == 0


@pytest.mark.parametrize(
    "native",
    [
        True,
        pytest.param(
            False,
            marks=pytest.mark.skipif(
                not (sys.platform == "linux" and redirect.supervises()),
                reason="no turn can be supervised here",
            ),
        ),
    ],
    ids=["native", "supervised"],
)
def test_a_turn_at_a_booked_meeting_is_told_where_it_is_and_no_ticket(
    sealed: Path, task: Path, tmp_path: Path, native: bool
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    broker = Broker("127.0.0.1", 0, punching=0.0, booked=True, tls=str(sealed))
    host, port = broker.start()
    serving, anchoring = broker.stand()
    peer = tmp_path / "peer"
    peer.write_text(f"{Meeting(serving, host, port, str(task))}\n")
    process = subprocess.Popen(
        [*SERVING_HALF, "--peer-file", str(peer), "--export", "/"],
        stdin=subprocess.DEVNULL,
    )
    target = f"peer://{Meeting(anchoring, host, port, str(sealed))}"
    try:
        line = AnchorConfig(
            target=target,
            workspace=str(workspace),
            shadow=None if native else str(tmp_path / "mirror"),
            native=native,
        ).command(["/bin/sh", "-c", 'printf "%s\\n" "$HUMANIZE_TARGET"; env'])
        done = subprocess.run(line, capture_output=True, timeout=120, check=False)
    finally:
        stopped(process)
        broker.close()

    assert done.returncode == 0, done.stderr.decode(errors="replace")[-2000:]
    told = done.stdout.decode(errors="replace")
    assert told.splitlines()[0] == f"peer://{host}:{port}"
    for secret in (anchoring, serving, str(sealed)):
        assert secret not in told


def test_a_meeting_is_told_without_its_ticket_or_its_certificate() -> None:
    sealed = transport.Target.parse("peer://t1cket@[::1]:7000?tls=/run/certs")
    assert sealed.told() == "peer://[::1]:7000"
    assert transport.Target.parse("peer://t1cket@broker:7000").told() == (
        "peer://broker:7000"
    )
    assert transport.Target.parse("ssh://box").told() == "ssh://box"
