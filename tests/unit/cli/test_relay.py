"""`hmz relay serve`: its line, its ready line, how it stops, and a relay that cannot listen.

The relay itself is a stand-in that listens nowhere; a stop is a signal this process sends
itself once the stand-in is entered.
"""

from __future__ import annotations

import contextlib
import os
import signal
from typing import TYPE_CHECKING

import pytest

import hmz.relay
from hmz.cli import main

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
def listened(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Where each relay was asked to listen; each is stopped by a terminate once it is."""
    asked: list[tuple[str, int]] = []

    @contextlib.asynccontextmanager
    async def listening(host: str, port: int) -> AsyncGenerator[int]:
        asked.append((host, port))
        os.kill(os.getpid(), signal.SIGTERM)
        yield port or 4321

    monkeypatch.setattr(hmz.relay, "listening", listening)
    return asked


def test_serve_listens_on_loopback_by_default_and_stops_on_a_terminate(
    listened: list[tuple[str, int]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["relay", "serve"]) == 0
    assert listened == [("127.0.0.1", 8765)]
    assert capsys.readouterr().out == "hmz relay: listening on ws://127.0.0.1:8765\n"


def test_serve_says_the_port_it_was_given(
    listened: list[tuple[str, int]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["relay", "serve", "--listen", "[::1]:0"]) == 0
    assert listened == [("::1", 0)]
    assert capsys.readouterr().out == "hmz relay: listening on ws://[::1]:4321\n"


def test_an_interrupt_stops_it_too(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @contextlib.asynccontextmanager
    async def listening(_host: str, port: int) -> AsyncGenerator[int]:
        os.kill(os.getpid(), signal.SIGINT)
        yield port

    monkeypatch.setattr(hmz.relay, "listening", listening)
    assert main(["relay", "serve", "--listen", "0.0.0.0:80"]) == 0
    assert capsys.readouterr().out == "hmz relay: listening on ws://0.0.0.0:80\n"


def test_a_relay_that_cannot_listen_says_why(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    @contextlib.asynccontextmanager
    async def listening(_host: str, _port: int) -> AsyncGenerator[int]:
        msg = "address already in use"
        raise OSError(msg)
        yield 0

    monkeypatch.setattr(hmz.relay, "listening", listening)
    assert main(["relay", "serve"]) == 1
    seen = capsys.readouterr()
    assert seen.out == ""
    assert seen.err == "hmz: the relay cannot listen: address already in use\n"


@pytest.mark.parametrize(
    "argv",
    [
        ["relay"],
        ["relay", "start"],
        ["relay", "serve", "--listen", "localhost"],
        ["relay", "serve", "--listen", ":80"],
        ["relay", "serve", "--listen", "localhost:65536"],
        ["relay", "serve", "--listen", "localhost:-1"],
        ["relay", "serve", "--listen", "localhost:http"],
        ["relay", "serve", "--listen", "::1:8765"],
        ["relay", "serve", "--listen", "[::1:8765"],
    ],
)
def test_anything_else_is_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        main(argv)
    assert exited.value.code == 2
    assert "hmz relay" in capsys.readouterr().err


def test_relay_is_listed_among_the_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "relay daemons and the devices that reach them" in capsys.readouterr().out
