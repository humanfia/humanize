"""`hmz.daemon.sessions`: one session's queue of what it is sent, and writes carried out once."""

from __future__ import annotations

import json
import struct
import threading
from typing import Any
from unittest import mock

import pytest

from hmz.daemon import sessions
from hmz.daemon.sessions import Idems, Outgoing, Session
from hmz.rpc import RpcError


def _frame(said: dict[str, Any]) -> bytes:
    payload = json.dumps(said).encode()
    return struct.pack(">I", len(payload)) + payload


def _told(sub: str, size: int = 0) -> bytes:
    return _frame(
        {
            "jsonrpc": "2.0",
            "method": "epic.event",
            "params": {"sub": sub, "message": {"text": "x" * size}},
        }
    )


def _answer(ident: int) -> bytes:
    return _frame({"jsonrpc": "2.0", "id": ident, "result": {}})


class _Pipe:
    """A pipe whose writes wait until it is let write, and are kept."""

    def __init__(self) -> None:
        self.wrote: list[bytes] = []
        self.flowing = threading.Event()
        self.closed = threading.Event()

    def recv(self, size: int) -> bytes:
        del size
        return b""

    def sendall(self, data: bytes) -> None:
        self.flowing.wait(5)
        self.wrote.append(data)

    def close(self) -> None:
        self.closed.set()


def test_what_is_queued_is_written_in_order() -> None:
    pipe = _Pipe()
    out = Outgoing(pipe, mock.Mock())
    pipe.flowing.set()
    out.sendall(_answer(1))
    out.sendall(_told("s1"))
    out.flush_then_close()

    assert pipe.closed.wait(5)
    assert pipe.wrote == [_answer(1), _told("s1")]


def test_a_session_too_far_behind_keeps_its_answers_and_drops_what_it_was_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sessions, "BEHIND", 1000)
    pipe = _Pipe()
    behind = mock.Mock()
    called = threading.Event()
    behind.side_effect = lambda: called.set()
    out = Outgoing(pipe, behind)
    out.sendall(_answer(0))  # being written while the rest wait
    out.sendall(_told("s1", 400))
    out.sendall(_answer(1))
    out.sendall(_told("s1", 400))
    assert called.wait(5)
    behind.assert_called_once()
    pipe.flowing.set()
    out.flush_then_close()

    assert pipe.closed.wait(5)
    assert pipe.wrote == [_answer(0), _answer(1)]


def test_a_closed_queue_takes_nothing() -> None:
    pipe = _Pipe()
    out = Outgoing(pipe, mock.Mock())
    out.close()

    assert pipe.closed.is_set()
    with pytest.raises(OSError, match="closed"):
        out.sendall(_answer(1))


def test_falling_behind_ends_every_subscription_of_the_session() -> None:
    out = mock.Mock(ended=set())
    session = Session(out, trusted=True, fingerprint="local", device="local")
    session.peer = mock.Mock()
    epic = mock.Mock()
    session.subs["s1"] = epic
    session.notices.add("s2")

    session.behind()

    epic.end.assert_called_once_with("too far behind; attach again")
    session.peer.notify.assert_called_once_with(
        "notices.event", {"sub": "s2", "gone": "too far behind; subscribe again"}
    )
    assert out.ended == {"s2"}


def test_a_session_is_paired_once_its_device_is_named() -> None:
    session = Session(mock.Mock(), trusted=False, fingerprint="f", device="")
    assert not session.paired
    session.device = "laptop"
    assert session.paired
    assert [session.named(), session.named()] == ["s1", "s2"]


def test_a_write_is_carried_out_once_per_device_and_key() -> None:
    idems = Idems()
    doing = mock.Mock(return_value={"run": 1})

    assert idems.once("d", "k", "epic.start", doing) == {"run": 1}
    assert idems.once("d", "k", "epic.start", doing) == {"run": 1}
    assert idems.once("e", "k", "epic.start", doing) == {"run": 1}
    assert doing.call_count == 2


def test_a_refusal_is_kept_as_the_answer() -> None:
    idems = Idems()
    doing = mock.Mock(side_effect=RpcError(409, "no"))

    for _ in range(2):
        with pytest.raises(RpcError, match="no"):
            idems.once("d", "k", "epic.say", doing)
    assert doing.call_count == 1


def test_a_key_used_for_another_method_is_refused() -> None:
    idems = Idems()
    idems.once("d", "k", "epic.say", dict)

    with pytest.raises(RpcError, match="used for another method") as refused:
        idems.once("d", "k", "epic.stop", dict)
    assert refused.value.code == 409


def test_an_answer_is_kept_ten_minutes() -> None:
    now = [0.0]
    idems = Idems(clock=lambda: now[0])
    doing = mock.Mock(return_value={})
    idems.once("d", "k", "epic.say", doing)
    now[0] = 601.0
    idems.once("d", "k", "epic.say", doing)

    assert doing.call_count == 2
