"""What `dial` opens for each route, with every socket, child and other package faked."""

from __future__ import annotations

import io
import json
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from websockets.exceptions import ConnectionClosedOK

import hmz.reach.relays
from hmz.daemon import where
from hmz.reach import (
    EasyTier,
    ProcessPipe,
    Route,
    SocketPipe,
    StreamPipe,
    WebSocketPipe,
    command,
    dial,
    join,
)

if TYPE_CHECKING:
    from hmz.rpc import Pipe

#: `hmz` connecting on the carrier handed on as descriptors 3 and 4.
CONNECTS = "exec hmz daemon connect --stdio <&3 >&4 3<&- 4>&-"


def connect(path: str) -> list[str]:
    """The login shell of the user, `/bin/sh` standing for it, asked only to run `/bin/sh`.

    What it prints goes to standard error and what it reads is nothing, the carrier kept
    for `hmz` as descriptors 3 and 4.
    """
    return [
        "/bin/sh",
        "-c",
        'exec "${SHELL:-/bin/sh}" -lc '
        + shlex.quote("exec /bin/sh -c " + shlex.quote(path + CONNECTS))
        + " 3<&0 4>&1 </dev/null >&2",
    ]


#: Over ssh and WSL: `~/.local/bin` in front of the `PATH` the login shell gives.
CONNECT = connect('PATH="$HOME/.local/bin:$PATH"; export PATH; ')

#: Here: `~/.local/bin` behind that `PATH`, where it lacks it.
LOCALLY = connect(
    'case ":$PATH:" in *":$HOME/.local/bin:"*) ;; '
    '*) PATH="$PATH:$HOME/.local/bin"; export PATH ;; esac; '
)

#: A daemon id, which an untrusted route is opened only with.
DAEMON = "d" * 52


class Road:
    """`hmz.coganchor.transport.Road`, answering with what it was asked to reach."""

    @classmethod
    def to(cls, target: Any) -> Road:
        road = cls()
        road.target = target
        return road

    target: Any = None

    def line(self, argv: list[str]) -> list[str]:
        return ["ssh-to", repr(self.target), *argv]


def test_stdio_local_runs_connect_through_a_login_shell() -> None:
    assert command(Route.parse("stdio:local")) == LOCALLY


def test_stdio_wsl_runs_it_in_the_distribution_named_or_the_default() -> None:
    assert command(Route.parse("stdio:wsl")) == ["wsl.exe", "--exec", *CONNECT]
    assert command(Route.parse("stdio:wsl:Ubuntu-22.04"))[:4] == [
        "wsl.exe",
        "-d",
        "Ubuntu-22.04",
        "--exec",
    ]


def test_stdio_ssh_runs_ssh_in_batch_mode_before_what_the_route_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("hmz.coganchor.transport.Road", Road)
    target = mock.Mock()
    monkeypatch.setattr("hmz.coganchor.transport.Target", target)
    route = Route.parse("stdio:ssh://me@box:2222?identity=k&jump=j&option=BatchMode=no")
    assert command(route)[-3:] == CONNECT
    target.assert_called_once_with(
        "ssh",
        host="me@box",
        port=2222,
        options=(
            ("BatchMode", "yes"),
            ("ConnectTimeout", "30"),
            ("IdentityFile", "k"),
            ("ProxyJump", "j"),
            ("BatchMode", "no"),
        ),
    )


def test_a_route_that_is_not_run_has_no_command() -> None:
    with pytest.raises(ValueError, match="is not run as a command"):
        command(Route.parse("tcp://box:1"))


def test_a_string_is_read_as_a_route_first() -> None:
    with pytest.raises(ValueError, match=r"^nonsense is not a route\.$"):
        dial("nonsense")


def test_webrtc_cannot_be_reached_from_a_native_client() -> None:
    with pytest.raises(
        ValueError, match=r"^webrtc:wss://relay cannot be reached from here\.$"
    ):
        dial("webrtc:wss://relay")


@pytest.mark.skipif(sys.platform == "win32", reason="WSL is reached from Windows")
def test_wsl_cannot_be_reached_but_from_windows() -> None:
    with pytest.raises(ValueError, match=r"^stdio:wsl cannot be reached from here\.$"):
        dial("stdio:wsl")


@pytest.mark.parametrize(
    "route", ["tcp://box:1", "ws://box", "easytier:home", "relay:ws://relay"]
)
def test_an_untrusted_route_needs_the_daemon_it_reaches_before_it_opens(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    opened = mock.Mock(side_effect=AssertionError("opened"))
    monkeypatch.setattr(socket, "create_connection", opened)
    monkeypatch.setattr("hmz.coganchor.easytier.joining", opened)
    monkeypatch.setattr(hmz.reach.relays, "websocket", opened)
    with pytest.raises(
        ValueError, match=rf"^{route} needs the id of the daemon it reaches\.$"
    ):
        dial(route, easytier={"home": EasyTier("s" * 16, ("tcp://n:1",))})
    opened.assert_not_called()


def test_a_carrier_not_open_in_time_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    hangs = mock.Mock(side_effect=TimeoutError("timed out"))
    monkeypatch.setattr(socket, "create_connection", hangs)
    with pytest.raises(
        TimeoutError, match=r"^tcp://box:1 did not open within 30 seconds\.$"
    ):
        dial("tcp://box:1", daemon=DAEMON)


def test_an_easytier_route_needs_an_entry_of_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    joining = mock.Mock()
    monkeypatch.setattr("hmz.coganchor.easytier.joining", joining)
    with pytest.raises(ValueError, match=r"^There is no EasyTier entry home\.$"):
        dial(
            "easytier:home",
            daemon=DAEMON,
            easytier={"work": EasyTier("s" * 16, ("tcp://n:1",))},
        )
    joining.assert_not_called()


def test_tcp_is_an_untrusted_connection_without_nagle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = mock.Mock(spec=socket.socket)
    connecting = mock.Mock(return_value=sock)
    monkeypatch.setattr(socket, "create_connection", connecting)
    pipe = dial("tcp://box:7000", daemon=DAEMON, timeout=3)
    assert isinstance(pipe, SocketPipe)
    assert not trusted(pipe)
    connecting.assert_called_once_with(("box", 7000), timeout=3)
    sock.settimeout.assert_called_once_with(None)
    sock.setsockopt.assert_called_once_with(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def test_unix_starts_this_machine_s_daemon_where_none_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sock = mock.Mock(spec=socket.socket)
    connects = mock.Mock(side_effect=[FileNotFoundError(), FileNotFoundError(), sock])
    monkeypatch.setattr(where, "at", lambda: Path("/daemon"))
    monkeypatch.setattr(where, "connects", connects)
    start = mock.Mock()
    pipe = dial("unix:", start=start)
    assert trusted(pipe)
    start.assert_called_once_with()
    assert connects.call_count == 3
    assert connects.call_args.args[0] == Path("/daemon")


def test_unix_without_a_way_to_start_one_fails_as_the_socket_did(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(where, "at", lambda: Path("/daemon"))
    monkeypatch.setattr(where, "connects", mock.Mock(side_effect=FileNotFoundError()))
    with pytest.raises(FileNotFoundError):
        dial("unix:")


def test_stdio_local_is_a_trusted_child(monkeypatch: pytest.MonkeyPatch) -> None:
    child = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO(), stderr=io.BytesIO())
    popen = mock.Mock(return_value=child)
    monkeypatch.setattr(subprocess, "Popen", popen)
    assert trusted(dial("stdio:local"))
    assert popen.call_args.args[0] == LOCALLY
    assert popen.call_args.kwargs["stdin"] == subprocess.PIPE
    assert popen.call_args.kwargs["stdout"] == subprocess.PIPE
    assert popen.call_args.kwargs["stderr"] == subprocess.PIPE


class Relay:
    """A connection to a relay, answering a join with what it is told to."""

    def __init__(self, *answers: str | bytes) -> None:
        self.answers = list(answers)
        self.sent: list[str | bytes] = []
        self.closed = False

    def send(self, message: str | bytes) -> None:
        self.sent.append(message)

    def recv(self, timeout: float | None = None) -> str | bytes:
        if not self.answers:
            raise ConnectionClosedOK(None, None)
        return self.answers.pop(0)

    def close(self) -> None:
        self.closed = True


def joins(monkeypatch: pytest.MonkeyPatch, relay: Relay) -> None:
    def opens(_url: str, _timeout: float) -> Relay:
        return relay

    monkeypatch.setattr(hmz.reach.relays, "websocket", opens)


def test_a_native_join_says_join_and_is_the_splice_once_joined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = Relay(json.dumps({"t": "joined"}))
    joins(monkeypatch, relay)
    pipe = dial("relay:wss://relay/r", daemon=DAEMON)
    assert isinstance(pipe, WebSocketPipe)
    assert not trusted(pipe)
    assert [json.loads(one) for one in relay.sent] == [
        {"t": "join", "id": DAEMON, "kind": "native"}
    ]
    assert not relay.closed


def test_a_join_refused_raises_what_the_relay_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = Relay(json.dumps({"t": "error", "why": "No daemon x is here."}))
    joins(monkeypatch, relay)
    with pytest.raises(ConnectionError, match=r"^No daemon x is here\.$"):
        join("ws://relay", "x")
    assert relay.closed


@pytest.mark.parametrize("answer", [b"binary first", "not json", '{"t": "signal"}'])
def test_a_join_answered_out_of_turn_is_no_join(
    monkeypatch: pytest.MonkeyPatch, answer: str | bytes
) -> None:
    relay = Relay(answer)
    joins(monkeypatch, relay)
    with pytest.raises(ConnectionError, match="answered no join"):
        join("ws://relay", "x")
    assert relay.closed


def test_a_relay_closing_before_it_answers_did_not_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relay = Relay()
    joins(monkeypatch, relay)
    with pytest.raises(ConnectionError, match="did not join"):
        join("ws://relay", "x")
    assert relay.closed


@pytest.mark.parametrize(
    "text",
    [
        "stdio:ssh://-oProxyCommand=evil",
        "stdio:ssh://a%20b",
        "stdio:ssh://-u@h",
    ],
)
def test_an_ssh_destination_ssh_would_misread_cannot_be_reached(text: str) -> None:
    with pytest.raises(ValueError, match=r"cannot be reached from here\.$"):
        command(Route.parse(text))


def trusted(pipe: Pipe) -> bool:
    """Whether a pipe `hmz.reach` made says its carrier is trusted."""
    assert isinstance(pipe, SocketPipe | ProcessPipe | StreamPipe | WebSocketPipe)
    return pipe.trusted
