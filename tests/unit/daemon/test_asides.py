"""`hmz.daemon.asides`: side questions about one session, asked on the host that holds it."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.daemon.asides import Asides
from hmz.rpc import RpcError
from hmz.runtime import Refused
from hmz.runtime.watching import btw, following

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.daemon.hosts import Subscription
    from hmz.rpc import Call


class _Following:
    """What the daemon follows of a host's epic: only the sessions it has seen."""

    def __init__(self) -> None:
        self.seen: dict[str, object] = {}

    def opened(self, message: dict[str, Any]) -> None:
        self.seen[str(message["key"])] = object()

    def started(self, message: dict[str, Any]) -> None:
        del message

    def printed(self, text: str) -> None:
        del text

    def heard(self, message: dict[str, Any]) -> None:
        del message

    def ended(self, message: dict[str, Any]) -> None:
        del message

    def close(self) -> None:
        pass

    def snapshot(self, **said: Any) -> str:
        return f"snapshot of {said['workspace']}"


class _Btw:
    """A side copy of one session, answering what it is asked."""

    made: list[_Btw]
    failing: Exception | None = None

    def __init__(self, target: str, **given: Any) -> None:
        self.target = target
        self.given = given
        self.asked: list[tuple[str, object]] = []
        self.closed: list[bool] = []
        self.forgot = 0
        _Btw.made.append(self)

    def ask(self, question: str, snapshot: object) -> str:
        self.asked.append((question, snapshot))
        if _Btw.failing is not None:
            raise _Btw.failing
        return f"{self.target} says: {question}"

    def close(self, *, unasking: bool = True) -> None:
        self.closed.append(unasking)

    def forget(self) -> None:
        self.forgot += 1


class _Hosted:
    """A host of one slot, telling each frontend the epic so far as it attaches."""

    def __init__(self, workspace: str, slot: str, epic: str, keys: list[str]) -> None:
        self.workspace, self.slot, self.epic = workspace, slot, epic
        self.subs: list[Subscription] = []
        self.keys = keys
        self.detached: list[str] = []

    def attach(self, sub: Subscription, *, replay: bool, since: object) -> str:
        assert (replay, since) == (True, None)
        self.subs.append(sub)
        sub.told({"type": "welcome"})
        # The epic so far, which a frontend attaching is told before it is live.
        sub.told({"type": "started", "seq": 1, "run": 1})
        for key in self.keys:
            sub.told({"type": "opened", "seq": 2, "key": key})
        sub.told({"type": "live", "seq": 2})
        return f"c{len(self.subs)}"

    def ask(self, client: str, said: dict[str, Any]) -> dict[str, Any]:
        del client, said
        return {"ok": True}

    def detach(self, client: str) -> None:
        self.detached.append(client)

    def status(self) -> dict[str, Any]:
        # A chat's host names its chat, and no epic.
        if self.slot.startswith("chat:"):
            return {"epic": "", "chat": self.epic}
        return {"epic": self.epic, "chat": ""}

    def forget(self, sub: Subscription) -> None:
        del sub


class _Hosts:
    def __init__(self, *held: _Hosted) -> None:
        self.held = {one.slot: one for one in held}
        self.opened_slots: list[str] = []

    def listed(self) -> list[_Hosted]:
        return list(self.held.values())

    def opened(self, workspace: str, slot: str) -> _Hosted:
        del workspace
        self.opened_slots.append(slot)
        return self.held[slot]


@pytest.fixture(autouse=True)
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    _Btw.made, _Btw.failing = [], None
    monkeypatch.setattr(btw, "Btw", _Btw)
    monkeypatch.setattr(following, "Following", _Following)


def _call(method: str, **params: Any) -> Call:
    return cast("Call", SimpleNamespace(method=method, params=params))


def _asides(tmp_path: Path, *held: _Hosted) -> tuple[Asides, _Hosts]:
    hosts = _Hosts(*held)
    return Asides(SimpleNamespace(hosts=hosts)), hosts  # pyright: ignore[reportArgumentType]


def _host(tmp_path: Path, slot: str = "", epic: str = "e1") -> _Hosted:
    return _Hosted(str(tmp_path), slot, epic, ["coder/1"])


def _ask(asides: Asides, tmp_path: Path, **said: Any) -> dict[str, Any]:
    return asides.ask(_call("btw.ask", workspace=str(tmp_path), **said))


def _listed(asides: Asides, tmp_path: Path, epic: str = "") -> list[dict[str, Any]]:
    return asides.listed(_call("btw.list", workspace=str(tmp_path), epic=epic))[
        "asides"
    ]


def test_a_side_question_is_answered_and_the_replayed_start_closes_nothing(
    tmp_path: Path,
) -> None:
    asides, _ = _asides(tmp_path, _host(tmp_path))

    first = _ask(asides, tmp_path, aside="a", to="coder/1", question="what  now?")
    second = _ask(asides, tmp_path, aside="a", to="coder/1", question="and then?")

    assert first == {
        "aside": "a",
        "to": "coder/1",
        "question": "what now?",
        "answer": "coder/1 says: what now?",
    }
    assert second["answer"] == "coder/1 says: and then?"
    # One side copy, asked twice, and never closed by the epic the host replayed.
    (made,) = _Btw.made
    assert [question for question, _ in made.asked] == ["what now?", "and then?"]
    assert made.closed == []
    assert made.asked[0][1] == f"snapshot of {tmp_path}"
    (listed,) = _listed(asides, tmp_path)
    assert listed["question"] == ""
    assert [one["answer"] for one in listed["said"]] == [
        "coder/1 says: what now?",
        "coder/1 says: and then?",
    ]


def test_an_epic_starting_once_live_closes_the_asides_about_the_epic_going(
    tmp_path: Path,
) -> None:
    hosted = _host(tmp_path)
    asides, _ = _asides(tmp_path, hosted)
    _ask(asides, tmp_path, aside="a", to="coder/1", question="q")

    hosted.subs[-1].told({"type": "started", "seq": 9, "run": 2})

    deadline = time.monotonic() + 5
    while _listed(asides, tmp_path) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _listed(asides, tmp_path) == []
    # The host closed it already, as an epic starts: nothing is asked of it to close it.
    assert _Btw.made[0].closed == [False]


def test_a_chat_is_asked_on_its_own_slot_by_its_name(tmp_path: Path) -> None:
    own, chat = _host(tmp_path, "", "e1"), _host(tmp_path, "chat:ab", "c2")
    asides, hosts = _asides(tmp_path, own, chat)

    said = _ask(asides, tmp_path, aside="a", to="coder/1", chat="c2", question="q")

    assert said["answer"] == "coder/1 says: q"
    assert hosts.opened_slots == ["chat:ab"]
    assert own.subs == []
    about = asides.listed(_call("btw.list", workspace=str(tmp_path), chat="c2"))
    assert about["asides"][0]["to"] == "coder/1"
    assert _listed(asides, tmp_path) == []
    assert _listed(asides, tmp_path, "e1") == []


@pytest.mark.parametrize("to", ["", "coder", "coder/0", "a b/1", "coder/x"])
def test_a_side_question_is_asked_of_a_session(tmp_path: Path, to: str) -> None:
    asides, hosts = _asides(tmp_path, _host(tmp_path))

    with pytest.raises(RpcError) as refused:
        _ask(asides, tmp_path, aside="a", to=to, question="q")

    assert refused.value.code == 400
    assert refused.value.message == (
        "A side question is asked of a session, as <agent>/<n>."
    )
    assert hosts.opened_slots == []


def test_a_session_the_epic_going_has_not_is_refused(tmp_path: Path) -> None:
    asides, _ = _asides(tmp_path, _host(tmp_path))

    with pytest.raises(RpcError) as refused:
        _ask(asides, tmp_path, aside="a", to="critic/1", question="q")

    assert (refused.value.code, refused.value.message) == (
        404,
        "critic/1 has no conversation to ask",
    )
    assert _listed(asides, tmp_path) == []


def test_an_aside_whose_first_question_fails_is_closed_and_not_kept(
    tmp_path: Path,
) -> None:
    asides, _ = _asides(tmp_path, _host(tmp_path))
    _Btw.failing = Refused("claude cannot answer a side question")

    with pytest.raises(RpcError) as refused:
        _ask(asides, tmp_path, aside="a", to="coder/1", question="q")

    assert (refused.value.code, refused.value.message) == (
        409,
        "claude cannot answer a side question",
    )
    # Nothing kept to hold the host for: it is let go of in time.
    assert _listed(asides, tmp_path) == []
    assert _Btw.made[0].closed == [True]


def test_an_aside_that_answered_is_kept_when_a_later_question_fails(
    tmp_path: Path,
) -> None:
    asides, _ = _asides(tmp_path, _host(tmp_path))
    _ask(asides, tmp_path, aside="a", to="coder/1", question="q")
    _Btw.failing = btw.Left()

    with pytest.raises(RpcError) as refused:
        _ask(asides, tmp_path, aside="a", to="coder/1", question="again")

    assert refused.value.code == 409
    assert len(_listed(asides, tmp_path)) == 1


def test_leaving_closes_one_aside_or_every_one(tmp_path: Path) -> None:
    asides, _ = _asides(tmp_path, _host(tmp_path))
    for name in ("a", "b", "c"):
        _ask(asides, tmp_path, aside=name, to="coder/1", question="q")

    asides.leave(_call("btw.leave", workspace=str(tmp_path), aside="b"))
    assert [one["aside"] for one in _listed(asides, tmp_path)] == ["a", "c"]

    asides.leave(_call("btw.leave", workspace=str(tmp_path)))
    assert _listed(asides, tmp_path) == []
    assert [one.closed for one in _Btw.made] == [[True], [True], [True]]


def test_the_host_going_closes_the_asides_about_its_epic(tmp_path: Path) -> None:
    hosted = _host(tmp_path)
    asides, _ = _asides(tmp_path, hosted)
    _ask(asides, tmp_path, aside="a", to="coder/1", question="q")

    hosted.subs[-1].told({"type": "gone", "why": "the host went away"})

    deadline = time.monotonic() + 5
    while _listed(asides, tmp_path) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _listed(asides, tmp_path) == []
    assert _Btw.made[0].closed == [False]
