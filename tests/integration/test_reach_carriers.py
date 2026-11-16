"""Carriers opened for real: stdio over `ssh`, TCP, EasyTier, and routes raced over them.

`ssh` and `easytier-core` are the stand-ins of `doubles_ssh` and `doubles_easytier`. What
answers at the far end is an echo, standing in for a daemon: L0 carries bytes and knows
nothing of what they say.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import easytier
from hmz.reach import (
    EasyTier,
    Pipe,
    ProcessPipe,
    Route,
    SocketPipe,
    StreamPipe,
    TcpListener,
    WebSocketPipe,
    dial,
    race,
)
from tests.integration import doubles_easytier, doubles_ssh

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SECRET = "correct horse battery staple"
NODES = ("tcp://node.example:11010",)


def echoes(accept: Callable[[], socket.socket]) -> None:
    """Answers every connection accepted with what it says, until accepting fails."""

    def answers(one: socket.socket) -> None:
        with one, contextlib.suppress(OSError):
            while said := one.recv(65536):
                one.sendall(said)

    while True:
        try:
            one = accept()
        except OSError:
            return
        threading.Thread(target=answers, args=(one,), daemon=True).start()


def round_trip(pipe: Pipe, said: bytes = b"hello, daemon") -> bytes:
    """What comes back over a pipe to an echo for what is written."""
    # Written while it is read, as a buffer each way holds less than a long write.
    writing = threading.Thread(target=pipe.sendall, args=(said,), daemon=True)
    writing.start()
    heard = b""
    while len(heard) < len(said):
        read = pipe.recv(len(said) - len(heard))
        if not read:
            break
        heard += read
    return heard


@pytest.fixture
def unix_echo() -> Iterator[Path]:
    """An echo on a Unix socket, at a path short enough to be one."""
    where = Path(tempfile.mkdtemp(prefix="e", dir=os.environ.get("TMPDIR", "/tmp")))
    path = where / "s"
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind(str(path))
    listening.listen()
    threading.Thread(
        target=echoes, args=(lambda: listening.accept()[0],), daemon=True
    ).start()
    yield path
    listening.close()
    path.unlink(missing_ok=True)
    where.rmdir()


def test_a_unix_route_names_a_socket_by_its_path(unix_echo: Path) -> None:
    pipe = dial(f"unix:{unix_echo}")
    assert trusted(pipe)
    assert round_trip(pipe) == b"hello, daemon"
    pipe.close()


def test_stdio_over_ssh_reaches_connect_stdio_spliced_to_the_daemon_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unix_echo: Path
) -> None:
    host = doubles_ssh.faked(tmp_path, monkeypatch)
    # The `hmz` there is `hmz daemon connect --stdio` as `hmz.reach` makes it: its standard
    # streams spliced to the socket of the daemon of that machine.
    there = host.home / ".local" / "bin" / "hmz"
    there.write_text(
        f"#!/bin/sh\n"
        f'[ "$*" = "daemon connect --stdio" ] || exit 64\n'
        f"exec {sys.executable} -c "
        f'"from hmz.reach import dial, splice, stdio; '
        f"splice(stdio(), dial('unix:{unix_echo}'))\"\n"
    )
    monkeypatch.setenv("HUMANIZE_SSH_REUSE", "off")
    pipe = dial("stdio:ssh://me@box:2222?identity=~%2Fkey&option=ServerAliveCountMax=2")
    assert trusted(pipe)
    assert round_trip(pipe) == b"hello, daemon"
    assert round_trip(pipe, b"x" * 300_000) == b"x" * 300_000
    pipe.close()
    (told,) = host.told()
    assert told[:8] == [
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
        "-o",
        "IdentityFile=~/key",
        "-o",
        "ServerAliveCountMax=2",
    ]
    assert told[told.index("-p") + 1] == "2222"
    assert "me@box" in told
    assert told[-1].startswith("exec sh -lc ")


def test_stdio_over_ssh_that_cannot_reach_the_host_fails_with_what_ssh_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles_ssh.faked(tmp_path, monkeypatch)
    monkeypatch.setenv("HUMANIZE_SSH_REUSE", "off")
    pipe = dial("stdio:ssh://unreachable.example")
    with pytest.raises(ConnectionError, match="Could not resolve hostname"):
        pipe.recv(1)
    pipe.close()


def test_tcp_is_listened_on_and_dialed_untrusted() -> None:
    listener = TcpListener("127.0.0.1", 0)
    assert listener.route == Route("tcp", host="127.0.0.1", port=listener.port)
    accepted: list[Pipe] = []
    taking = threading.Thread(target=lambda: accepted.append(listener.accept()))
    taking.start()
    pipe = dial(str(listener.route))
    taking.join(5)
    (far,) = accepted
    assert not trusted(pipe)
    assert not trusted(far)
    pipe.sendall(b"to the daemon")
    assert far.recv(64) == b"to the daemon"
    far.sendall(b"to the client")
    assert pipe.recv(64) == b"to the client"
    pipe.close()
    assert far.recv(64) == b""
    far.close()
    listener.close()
    with pytest.raises(OSError):  # noqa: PT011 -- closed, whatever errno says
        listener.accept()


def test_a_listener_on_any_address_is_routed_to_by_this_machine_s_name() -> None:
    listener = TcpListener("0.0.0.0", 0)  # noqa: S104 -- what the spec may say
    try:
        assert listener.route == Route(
            "tcp", host=socket.gethostname(), port=listener.port
        )
    finally:
        listener.close()


def test_easytier_joins_and_dials_the_daemon_port_it_forwards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = doubles_easytier.faked(tmp_path, monkeypatch)
    # The daemon's side: its port on its loopback, which its EasyTier lets the network reach.
    daemon = socket.create_server(("127.0.0.1", 0))
    port: int = daemon.getsockname()[1]
    monkeypatch.setattr(easytier, "PORT", port)
    threading.Thread(
        target=echoes, args=(lambda: daemon.accept()[0],), daemon=True
    ).start()
    serving = easytier.serving(SECRET, port, peers=NODES)
    try:
        entries = {"home": EasyTier(SECRET, NODES)}
        pipe = dial("easytier:home", easytier=entries)
        assert not trusted(pipe)
        assert round_trip(pipe) == b"hello, daemon"
        # The two ends write their runs down in whichever order they start in.
        runs = [json.loads(line) for line in core.log.read_text().splitlines()]
        (joining,) = [run for run in runs if "--port-forward" in run["argv"]]
        joined = joining["argv"]
        assert joining["secret"]
        assert joined[joined.index("--port-forward") + 1].endswith(f":{port}")
        assert SECRET not in " ".join(" ".join(run["argv"]) for run in runs)
        # Closing the carrier stops the EasyTier started for it.
        pid = joining["pid"]
        pipe.close()
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        serving.terminate()
        serving.wait()
        daemon.close()


def test_routes_race_and_the_second_wins_where_the_first_hangs() -> None:
    hangs = TcpListener("127.0.0.1", 0)
    held: list[Pipe] = []
    threading.Thread(target=lambda: held.append(hangs.accept()), daemon=True).start()
    answers = TcpListener("127.0.0.1", 0)

    def greets() -> None:
        far = answers.accept()
        far.sendall(b"hello")

    threading.Thread(target=greets, daemon=True).start()

    def handshake(pipe: Pipe) -> bytes:
        said = pipe.recv(5)
        if not said:
            raise ConnectionError("closed before it said hello")
        return said

    began = time.monotonic()
    won = race([str(hangs.route), str(answers.route)], dial, handshake)
    assert won.route == str(answers.route)
    assert won.answer == b"hello"
    assert 0.25 <= time.monotonic() - began < 5
    # The loser was closed, as its far end sees.
    (loser,) = held
    assert loser.recv(1) == b""
    won.pipe.close()
    hangs.close()
    answers.close()


def trusted(pipe: Pipe) -> bool:
    """Whether a pipe `hmz.reach` made says its carrier is trusted."""
    assert isinstance(pipe, SocketPipe | ProcessPipe | StreamPipe | WebSocketPipe)
    return pipe.trusted
