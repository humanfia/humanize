"""`hmz.daemon.carrying`: a host's end of its link to the daemon, and what it prints and logs."""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from hmz.daemon import where
from hmz.daemon.carrying import HOST_LOG, Carrier, Printed, keeps, logged

if TYPE_CHECKING:
    from pathlib import Path


def test_the_host_log_is_a_file_name() -> None:
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


class _Call:
    """A call of the daemon's down the link, and how it was answered."""

    def __init__(self, method: str, **params: Any) -> None:
        self.method = method
        self.params = params
        self.answered = threading.Event()
        self.said: dict[str, Any] = {}

    def answer(self, result: Any) -> None:
        self.said = {"result": result}
        self.answered.set()

    def fail(self, error: Any) -> None:
        self.said = {"error": error.message}
        self.answered.set()


def _carried(carrier: Carrier, method: str, **params: Any) -> dict[str, Any]:
    call = _Call(method, **params)
    carrier.serve(call)  # pyright: ignore[reportArgumentType]
    assert call.answered.wait(5)
    return call.said


@pytest.fixture
def host() -> mock.Mock:
    held = mock.Mock(closed=False)
    held.attach.return_value = "c1"
    held.status.return_value = {"clients": [{"client": "c1"}, {"client": "c2"}]}
    held.asked.return_value = {"ok": True, "run": 1}
    return held


def test_attach_takes_a_frontend_on_and_tells_its_messages_up_the_link(
    host: mock.Mock,
) -> None:
    carrier = Carrier(host, {"pid": 1})
    carrier.peer = mock.Mock()

    said = _carried(
        carrier,
        "attach",
        tag="t1",
        name="ana",
        kind="tui",
        replay=False,
        since={"epoch": "e", "seq": 4},
    )

    assert said == {"result": {"client": "c1"}}
    assert carrier.ever
    name, kind, heard = host.attach.call_args.args
    assert (name, kind) == ("ana", "tui")
    assert host.attach.call_args.kwargs == {"replay": False, "since": ("e", 4)}
    heard({"type": "live"})
    carrier.peer.notify.assert_called_once_with(
        "told", {"tag": "t1", "message": {"type": "live"}}
    )


def test_ask_is_answered_as_the_host_answers(host: mock.Mock) -> None:
    carrier = Carrier(host, {})

    said = _carried(carrier, "ask", client="c1", said={"do": "start"})

    assert said == {"result": {"ok": True, "run": 1}}
    host.asked.assert_called_once_with("c1", {"do": "start"})


def test_a_chat_is_asked_from_outside_every_frontend(host: mock.Mock) -> None:
    host.chatted.return_value = {"ok": False, "why": "no", "code": 400}
    carrier = Carrier(host, {})

    said = _carried(carrier, "chat", said={"do": "say", "text": "/clear"})

    assert said == {"result": {"ok": False, "why": "no", "code": 400}}
    host.chatted.assert_called_once_with({"do": "say", "text": "/clear"})


def test_env_is_answered_as_the_host_answers_it_attaching_nobody(
    host: mock.Mock,
) -> None:
    host.env.return_value = {"ok": True, "envs": []}

    said = _carried(Carrier(host, {}), "env", said={"do": "hosts.env.list"})

    assert said == {"result": {"ok": True, "envs": []}}
    host.env.assert_called_once_with({"do": "hosts.env.list"})
    host.attach.assert_not_called()


def test_status_says_what_the_host_said_of_itself(host: mock.Mock) -> None:
    carrier = Carrier(host, {"pid": 7, "kind": "host"})

    said = _carried(carrier, "status")

    assert said["result"]["pid"] == 7
    assert said["result"]["clients"] == [{"client": "c1"}, {"client": "c2"}]


def test_detach_all_lets_every_frontend_go(host: mock.Mock) -> None:
    said = _carried(Carrier(host, {}), "detach_all")

    assert said == {"result": {"let_go": 2}}
    assert host.detach.call_args_list == [mock.call("c1"), mock.call("c2")]


def test_a_call_that_fails_is_answered_as_one(host: mock.Mock) -> None:
    host.attach.side_effect = RuntimeError("this host has closed")

    said = _carried(Carrier(host, {}), "attach", tag="t", name="", kind="sdk")

    assert said == {"error": "Something went wrong here: this host has closed"}


def test_close_closes_the_host(host: mock.Mock) -> None:
    closed = threading.Event()
    host.close.side_effect = closed.set
    call = _Call("close")

    Carrier(host, {}).serve(call)  # pyright: ignore[reportArgumentType]

    assert closed.wait(5)
    assert not call.answered.is_set()
