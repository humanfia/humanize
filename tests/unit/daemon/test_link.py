"""`hmz.daemon.link`: one frontend's end of a workspace's runs, however it reached them."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pydantic
import pytest

from hmz.daemon import where
from hmz.daemon.link import Link, linked, reached
from hmz.daemon.proto import GONE, MESSAGE, frame, spoken
from hmz.runtime import Refused
from tests.unit.daemon.wire_u1 import Wire

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping


class _Asked:
    """What a link's requests go to: answering each with `answer`, and keeping them."""

    def __init__(self, answer: Mapping[str, Any] | None = None) -> None:
        self.said: list[dict[str, Any]] = []
        self.seconds: list[float | None] = []
        self.answer = {"ok": True} if answer is None else dict(answer)
        self.left = 0

    def asks(self, said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        self.said.append(said)
        self.seconds.append(seconds)
        return self.answer

    def leaves(self) -> None:
        self.left += 1


def _link(answer: Mapping[str, Any] | None = None) -> tuple[Link, _Asked]:
    held = _Asked(answer)
    return Link(held.asks, held.leaves), held


def test_asked_hands_back_an_answer_that_is_ok() -> None:
    link, held = _link({"ok": True, "run": 3})
    assert link.asked({"do": "status"}, seconds=2.0) == {"ok": True, "run": 3}
    assert held.said == [{"do": "status"}]
    assert held.seconds == [2.0]


@pytest.mark.parametrize(
    ("answer", "why"),
    [({"ok": False, "why": "no such flow"}, "no such flow"), ({}, "refused")],
)
def test_asked_raises_a_refusal_as_the_runtimes_own(
    answer: dict[str, Any], why: str
) -> None:
    link, _ = _link(answer)
    with pytest.raises(Refused, match=why):
        link.asked({"do": "start"})


class _Params(pydantic.BaseModel):
    rounds: int = 2


@pytest.mark.parametrize(
    ("params", "plain"),
    [(None, None), ({"rounds": 4}, {"rounds": 4}), (_Params(), {"rounds": 2})],
)
def test_start_writes_out_the_whole_request(params: Any, plain: Any) -> None:
    link, held = _link()
    link.start(
        Path("flows/chat"),
        "say hello",
        agents={"assistant": "claude"},
        envs={"box": "local"},
        params=params,
        budget={"cost": 5},
        profile=True,
    )
    assert held.said == [
        {
            "do": "start",
            "flow": str(Path("flows/chat")),
            "task": "say hello",
            "agents": {"assistant": "claude"},
            "envs": {"box": "local"},
            "params": plain,
            "budget": {"cost": 5},
            "profile": True,
            "resume": False,
        }
    ]


@pytest.mark.parametrize(
    ("resume", "said"),
    [(True, True), (False, False), (Path("epics/1"), str(Path("epics/1"))), ("e", "e")],
)
def test_start_says_which_run_to_pick_up(resume: Any, said: object) -> None:
    link, held = _link()
    link.start("chat", "t", resume=resume)
    assert held.said[0]["resume"] == said
    assert held.said[0]["agents"] == {}
    assert held.said[0]["envs"] == {}
    assert held.said[0]["budget"] is None


@pytest.mark.parametrize(
    ("name", "args", "kwargs", "expected"),
    [
        ("say", ["hi"], {}, {"do": "say", "text": "hi", "to": ""}),
        ("say", ["hi"], {"to": "c"}, {"do": "say", "text": "hi", "to": "c"}),
        (
            "answer",
            ["q1", "yes"],
            {},
            {"do": "answer", "question": "q1", "text": "yes"},
        ),
        ("stop", [], {}, {"do": "stop"}),
        ("force", [], {}, {"do": "force"}),
        ("afk", [], {"on": True}, {"do": "afk", "on": True, "role": ""}),
        (
            "afk",
            [],
            {"on": False, "role": "r"},
            {"do": "afk", "on": False, "role": "r"},
        ),
        ("claim", ["r"], {}, {"do": "claim", "role": "r", "take": False}),
        ("claim", ["r"], {"take": True}, {"do": "claim", "role": "r", "take": True}),
        ("release", ["r"], {}, {"do": "release", "role": "r"}),
        ("board", ["k", "v"], {}, {"do": "board", "key": "k", "value": "v"}),
        (
            "aside",
            [],
            {"agent": "a", "text": "t"},
            {"do": "aside", "agent": "a", "text": "t"},
        ),
    ],
)
def test_each_request_is_the_one_the_protocol_names(
    name: str, args: list[Any], kwargs: dict[str, Any], expected: dict[str, Any]
) -> None:
    link, held = _link({"ok": True, "x": 1})
    asks: Callable[..., dict[str, Any]] = getattr(link, name)
    assert asks(*args, **kwargs) == {"ok": True, "x": 1}
    assert held.said == [expected]


def test_iterating_yields_what_it_is_told_up_to_gone() -> None:
    link, _ = _link()
    for message in ({"type": "a"}, {"type": "gone"}, {"type": "after"}):
        link.told(message)
    assert list(link) == [{"type": "a"}, {"type": "gone"}]


def test_closing_ends_iteration_and_lets_go_once() -> None:
    link, held = _link()
    link.told({"type": "a"})
    with link as same:
        assert same is link
    link.close()
    assert list(link) == [{"type": "a"}]
    assert held.left == 1


def test_closing_survives_a_leave_that_fails() -> None:
    link = Link(lambda said, seconds: {"ok": True}, mock.Mock(side_effect=OSError))
    link.close()
    assert list(link) == []


def test_heard_hands_every_message_to_the_listener_in_order() -> None:
    link, _ = _link()
    link.told({"n": 1})
    got: list[dict[str, Any]] = []
    done = threading.Event()

    def listens(message: dict[str, Any]) -> None:
        got.append(message)
        if message.get("type") == "gone":
            done.set()

    link.heard(listens)
    link.told({"n": 2})
    link.told({"type": "gone"})
    assert done.wait(5)
    assert got == [{"n": 1}, {"n": 2}, {"type": "gone"}]


def test_heard_survives_a_listener_that_raises() -> None:
    link, _ = _link()
    done = threading.Event()

    def listens(message: dict[str, Any]) -> None:
        if message.get("n") == 1:
            raise RuntimeError
        done.set()

    link.heard(listens)
    link.told({"n": 1})
    link.told({"n": 2})
    assert done.wait(5)


def test_a_link_takes_one_listener_and_is_then_not_iterated() -> None:
    link, _ = _link()
    link.heard(lambda message: None)
    with pytest.raises(RuntimeError, match="already has a listener"):
        link.heard(lambda message: None)
    with pytest.raises(RuntimeError, match="go to its listener"):
        iter(link)
    link.close()


def test_linked_attaches_to_runs_held_in_this_process() -> None:
    host = mock.Mock()
    host.attach.return_value = "c7"
    host.asked.return_value = {"ok": True, "flows": []}
    link = linked(host, "me", "cli", replay=False)
    assert link.client == "c7"
    ((name, kind, told), keywords) = host.attach.call_args
    assert (name, kind, keywords) == ("me", "cli", {"replay": False})
    told({"type": "x"})
    assert link.asked({"do": "status"}) == {"ok": True, "flows": []}
    host.asked.assert_called_once_with("c7", {"do": "status"})
    link.close()
    host.detach.assert_called_once_with("c7")
    assert list(link) == [{"type": "x"}]


def _host(
    *, hello: Mapping[str, Any] | None = None, then: Iterable[bytes] = ()
) -> Callable[[bytes, dict[str, Any]], list[bytes]]:
    """A host answering `hello` with `hello`, and anything after with an ok, then `then`."""
    pending = list(then)

    def answers(kind: bytes, said: dict[str, Any]) -> list[bytes]:
        assert kind == MESSAGE
        if said["do"] == "hello":
            answer = dict(hello or {"ok": True, "client": "c1"})
        else:
            answer = {"ok": True, "did": said["do"]}
        reply = spoken(MESSAGE, {"type": "reply", "to": said["id"], **answer})
        out = [reply, *pending]
        pending.clear()
        return out

    return answers


@pytest.fixture
def wires(monkeypatch: pytest.MonkeyPatch) -> list[Wire]:
    """Every connection made through `where.connects`, the next to be made first."""
    made: list[Wire] = []

    def connects(at: Path, seconds: float | None = None) -> Wire:
        del at, seconds
        return made.pop(0)

    monkeypatch.setattr(where, "connects", connects)
    return made


def test_reached_says_hello_and_takes_its_client_id(
    wires: list[Wire], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_NAME", "ada")
    wire = Wire(_host())
    wires.append(wire)
    link = reached(tmp_path, "/w", kind="tui", replay=False)
    assert link.client == "c1"
    kind, hello = wire.sent[0]
    assert kind == MESSAGE
    assert {k: v for k, v in hello.items() if k != "id"} == {
        "do": "hello",
        "workspace": "/w",
        "name": "ada@tui",
        "kind": "tui",
        "replay": False,
    }
    assert link.stop() == {"ok": True, "did": "stop"}
    link.close()
    assert wire.closed


def test_reached_names_the_frontend_as_asked(wires: list[Wire], tmp_path: Path) -> None:
    wire = Wire(_host())
    wires.append(wire)
    reached(tmp_path, "/w", "ci").close()
    assert wire.sent[0][1]["name"] == "ci"


def test_reached_turns_a_refused_hello_into_an_os_error(
    wires: list[Wire], tmp_path: Path
) -> None:
    wire = Wire(_host(hello={"ok": False, "why": "no runs are held in /w"}))
    wires.append(wire)
    with pytest.raises(OSError, match="no runs are held"):
        reached(tmp_path, "/w")
    assert wire.closed


def test_reached_passes_messages_on_and_ends_with_gone(
    wires: list[Wire], tmp_path: Path
) -> None:
    told = spoken(MESSAGE, {"type": "said", "text": "hi"})
    wire = Wire(
        _host(then=[told, spoken(MESSAGE, {"type": "gone", "why": "done"}), b""])
    )
    wires.append(wire)
    link = reached(tmp_path, "/w")
    assert list(link) == [
        {"type": "said", "text": "hi"},
        {"type": "gone", "why": "done"},
    ]
    with pytest.raises(Refused, match="done"):
        link.stop()


def test_reached_reads_a_daemon_of_another_protocol_as_gone(
    wires: list[Wire], tmp_path: Path
) -> None:
    wire = Wire(_host(then=[frame(GONE, b"held by a newer humanize")]))
    wires.append(wire)
    link = reached(tmp_path, "/w")
    assert list(link) == [{"type": "gone", "why": "held by a newer humanize"}]


def test_reached_says_the_host_went_away_when_it_closes(
    wires: list[Wire], tmp_path: Path
) -> None:
    wire = Wire(_host(then=[b""]))
    wires.append(wire)
    link = reached(tmp_path, "/w")
    assert list(link) == [{"type": "gone", "why": "the host went away"}]


def test_reached_refuses_what_cannot_be_sent(wires: list[Wire], tmp_path: Path) -> None:
    wire = Wire(_host())
    wires.append(wire)
    link = reached(tmp_path, "/w")
    wire.closed = True
    with pytest.raises(Refused, match="could not be reached"):
        link.say("hi")
    wire.say(b"")
