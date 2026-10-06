"""`hmz.daemon.routing`: what this machine's daemon does with each connection it takes."""

from __future__ import annotations

import os
import struct
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon import where
from hmz.daemon.carrying import TAKEN
from hmz.daemon.proto import CONTROL, GONE, MESSAGE, frame, spoken
from hmz.daemon.routing import Router
from tests.unit.daemon.wire_u1 import Wire

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


class _Listening:
    """A listening socket handing out the connections it was given, then failing."""

    def __init__(self, *arriving: Wire | Callable[[], object]) -> None:
        self._arriving = list(arriving)
        self.closed = False

    def settimeout(self, seconds: float | None) -> None:
        del seconds

    def accept(self) -> tuple[Wire, str]:
        while self._arriving:
            one = self._arriving.pop(0)
            if isinstance(one, Wire):
                return one, ""
            one()
        raise OSError("no more")

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def routed(tmp_path: Path) -> Iterator[Callable[..., Router]]:
    """A router taking the connections given, closed after the test."""
    made: list[Router] = []

    def routes(*arriving: Wire | Callable[[], object]) -> Router:
        router = Router(_Listening(*arriving), tmp_path)  # pyright: ignore[reportArgumentType]
        made.append(router)
        router.start()
        return router

    yield routes
    for router in made:
        router.close()


def _answer(wire: Wire) -> list[tuple[bytes, dict[str, Any]]]:
    assert wire.ended.wait(5)
    return wire.sent


def test_a_router_that_can_take_nothing_more_is_over(
    routed: Callable[..., Router],
) -> None:
    router = routed()
    assert router.wait(5)


def test_closing_takes_the_socket_and_its_note_away(
    tmp_path: Path, routed: Callable[..., Router]
) -> None:
    for name in (where.SOCKET, where.RECORD, where.LOG):
        (tmp_path / name).write_text("")
    router = routed()
    router.close()
    assert router.wait(0)
    assert sorted(one.name for one in tmp_path.iterdir()) == [where.LOG]


def test_listing_with_no_host_is_an_empty_list(routed: Callable[..., Router]) -> None:
    wire = Wire(arriving=[spoken(CONTROL, {"do": "list"})])
    routed(wire)
    assert _answer(wire) == [(CONTROL, {"ok": True, "held": []})]


def test_a_question_it_does_not_know_is_refused(routed: Callable[..., Router]) -> None:
    wire = Wire(arriving=[spoken(CONTROL, {"do": "dance"})])
    routed(wire)
    assert _answer(wire) == [
        (CONTROL, {"ok": False, "why": "no such request: 'dance'"})
    ]


@pytest.mark.parametrize(
    ("kind", "said", "answer"),
    [
        (
            MESSAGE,
            {"do": "hello", "workspace": "/w", "id": "r1"},
            {"type": "reply", "to": "r1", "ok": False, "why": "no runs are held in /w"},
        ),
        (
            MESSAGE,
            {"do": "hello", "workspace": ""},
            {
                "type": "reply",
                "to": "",
                "ok": False,
                "why": "no runs are held in no workspace",
            },
        ),
        (
            CONTROL,
            {"do": "status", "workspace": "/w"},
            {"ok": False, "why": "no runs are held in /w"},
        ),
    ],
)
def test_a_workspace_nobody_holds_is_said_to_be_held_by_nobody(
    routed: Callable[..., Router],
    kind: bytes,
    said: dict[str, Any],
    answer: dict[str, Any],
) -> None:
    wire = Wire(arriving=[spoken(kind, said)])
    routed(wire)
    assert _answer(wire) == [(kind, answer)]


def test_a_reader_of_another_protocol_is_told_so(
    routed: Callable[..., Router],
) -> None:
    wire = Wire(arriving=[frame(b"Z", b"{}")])
    routed(wire)
    assert _answer(wire) == [(GONE, {})]
    assert b"newer humanize" in wire.raw[0]


@pytest.mark.parametrize(
    "arriving",
    [b"", MESSAGE + struct.pack(">I", 1 << 30)],
    ids=["closed", "not-a-frame"],
)
def test_a_connection_saying_nothing_of_this_protocol_is_closed(
    routed: Callable[..., Router], arriving: bytes
) -> None:
    wire = Wire(arriving=[arriving])
    routed(wire)
    assert _answer(wire) == []


def test_a_host_is_taken_on_and_then_listed(routed: Callable[..., Router]) -> None:
    host = Wire(
        arriving=[
            spoken(
                CONTROL,
                {"do": "serve", "pid": 7, "workspace": "/w", "started": "t"},
            )
        ]
    )
    asking = Wire(arriving=[spoken(CONTROL, {"do": "list"})])
    routed(host, lambda: host.wrote.wait(5), asking)

    assert _answer(asking) == [
        (CONTROL, {"ok": True, "held": [{"pid": 7, "workspace": "/w", "started": "t"}]})
    ]
    assert host.raw == [TAKEN]
    assert not host.closed


def test_a_second_host_of_a_workspace_held_by_a_live_one_is_refused(
    routed: Callable[..., Router],
) -> None:
    serve = {"do": "serve", "pid": os.getpid(), "workspace": "/w", "started": "t"}
    first = Wire(arriving=[spoken(CONTROL, serve)])
    second = Wire(arriving=[spoken(CONTROL, serve)])
    routed(first, lambda: first.wrote.wait(5), second)
    assert _answer(second) == []
    assert second.raw == []
    assert first.raw == [TAKEN]


def test_a_host_with_no_workspace_is_refused(routed: Callable[..., Router]) -> None:
    wire = Wire(arriving=[spoken(CONTROL, {"do": "serve", "pid": 7})])
    routed(wire)
    assert _answer(wire) == []
    assert wire.raw == []
