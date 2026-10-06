"""`hmz.daemon.carrying`: what a host process prints and logs, and how it says what it holds."""

from __future__ import annotations

import errno
import os
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from hmz.daemon import where
from hmz.daemon.carrying import HOST_LOG, TAKEN, Carrier, Printed, keeps, logged, serves
from hmz.daemon.proto import CONTROL, PROTOCOL
from tests.unit.daemon.wire_u1 import Wire

if TYPE_CHECKING:
    from pathlib import Path


def test_taken_is_one_byte_and_the_host_log_a_file_name() -> None:
    assert len(TAKEN) == 1
    assert "/" not in HOST_LOG


def test_printed_says_each_whole_line_and_holds_the_rest() -> None:
    host = mock.Mock()
    printed = Printed(host)
    assert printed.writable()
    assert printed.encoding == "utf-8"
    assert printed.write("one\ntw") == len("one\ntw")
    assert host.printed.call_args_list == [mock.call("one")]
    printed.write("o\n\nthree")
    assert host.printed.call_args_list == [
        mock.call("one"),
        mock.call("two"),
        mock.call(""),
    ]


def test_printed_is_a_stream_print_writes_to() -> None:
    host = mock.Mock()
    print("hello", "there", file=Printed(host))
    host.printed.assert_called_once_with("hello there")


def test_logged_writes_what_was_being_done_to_descriptor_two(
    capfd: pytest.CaptureFixture[str],
) -> None:
    def fails() -> None:
        raise ValueError("boom")

    logged("plain")
    try:
        fails()
    except ValueError:
        logged("handling")
    err = capfd.readouterr().err
    assert err.startswith("plain\n")
    assert "handling\nTraceback" in err
    assert "ValueError: boom" in err


def _kept(host: object, *pieces: bytes) -> None:
    reading, writing = os.pipe()
    for piece in pieces:
        os.write(writing, piece)
    os.close(writing)
    try:
        keeps(reading, host)  # pyright: ignore[reportArgumentType]
    finally:
        os.close(reading)


def test_keeps_writes_into_the_epic_of_the_run_held(tmp_path: Path) -> None:
    host = mock.Mock(epic=tmp_path)
    _kept(host, b"one\n", b"two\n")
    assert (tmp_path / HOST_LOG).read_bytes() == b"one\ntwo\n"


def test_keeps_writes_beside_the_daemon_before_any_run_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(where, "at", lambda: tmp_path)
    _kept(mock.Mock(epic=None), b"early\n")
    assert (tmp_path / where.LOG).read_bytes() == b"early\n"


def test_keeps_survives_an_epic_that_cannot_be_written(tmp_path: Path) -> None:
    _kept(mock.Mock(epic=tmp_path / "missing"), b"lost\n")
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("answer", [b"", b"-"], ids=["closed", "refused"])
def test_serves_refuses_a_workspace_another_host_holds(
    monkeypatch: pytest.MonkeyPatch, answer: bytes
) -> None:
    wire = Wire(arriving=[answer])

    def connects(at: Path, seconds: float | None = None) -> Wire:
        del at, seconds
        return wire

    monkeypatch.setattr(where, "connects", connects)
    host = mock.Mock()
    with pytest.raises(OSError, match="already held") as raised:
        serves(host, "/w")
    assert raised.value.errno == errno.EADDRINUSE
    assert wire.closed
    ((kind, said),) = wire.sent
    assert kind == CONTROL
    assert said["do"] == "serve"
    assert said["workspace"] == "/w"
    assert said["pid"] == os.getpid()
    assert said["kind"] == "host"
    assert said["protocol"] == PROTOCOL
    host.close.assert_not_called()


def test_serves_raises_where_the_daemon_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuses(at: Path, seconds: float | None = None) -> Wire:
        raise ConnectionRefusedError

    monkeypatch.setattr(where, "connects", refuses)
    with pytest.raises(ConnectionRefusedError):
        serves(mock.Mock(), "/w")


def test_a_carrier_not_started_closes_its_connection() -> None:
    wire = Wire()
    carrier = Carrier(mock.Mock(), wire, {})  # pyright: ignore[reportArgumentType]
    assert not carrier.wait(0)
    carrier.close()
    carrier.close()
    assert wire.closed
