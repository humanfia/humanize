"""`hmz.daemon.link`: one frontend's end of a workspace's runs, however it reached them."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pydantic
import pytest

import hmz.daemon.link
from hmz.daemon.link import Link, linked, reached, remote
from hmz.runtime import Refused

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
        profile_flow=True,
        profile_environment=True,
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
            "profile_flow": True,
            "profile_environment": True,
            "resume": False,
            "backup": None,
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
    ("backup", "said"), [(None, None), ((), []), (("lab", "home"), ["lab", "home"])]
)
def test_start_says_where_the_epic_is_backed_up(backup: Any, said: object) -> None:
    link, held = _link()
    link.start("chat", "t", backup=backup)
    assert held.said[0]["backup"] == said


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


class _Pending:
    def __init__(self, answer: Any) -> None:
        self._answer = answer
        self.cancelled = False

    def result(self, timeout: float | None = None) -> Any:
        if self._answer is TimeoutError:
            raise TimeoutError
        if isinstance(self._answer, BaseException):
            raise self._answer
        return self._answer

    def cancel(self) -> None:
        self.cancelled = True


class _Daemon:
    """A session with a daemon, as `dialed` gives one: answering each method as told."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.serve: Callable[[Any], None] | None = None
        self.closed = threading.Event()

    def dialed(
        self, at: Path, name: str, kind: str, *, serve: Callable[[Any], None]
    ) -> tuple[_Daemon, dict[str, Any]]:
        self.calls.append(("session.hello", {"name": name, "kind": kind, "at": at}))
        self.serve = serve
        return self, {}

    def request(self, method: str, params: dict[str, Any]) -> _Pending:
        self.calls.append((method, params))
        return _Pending(self.answers.get(method, {}))

    def call(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        del timeout
        return self.request(method, params).result()

    def tells(self, sub: str, message: dict[str, Any]) -> None:
        assert self.serve is not None
        call = mock.Mock(method="epic.event", params={"sub": sub, "message": message})
        self.serve(call)

    def close(self) -> None:
        self.closed.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self.closed.wait(timeout)


@pytest.fixture
def daemon_(monkeypatch: pytest.MonkeyPatch) -> _Daemon:
    held = _Daemon({"epic.attach": {"sub": "s1", "client": "c3"}})
    monkeypatch.setattr(hmz.daemon.link, "dialed", held.dialed)
    return held


def test_reached_says_hello_and_attaches(daemon_: _Daemon, tmp_path: Path) -> None:
    link = reached(tmp_path, "/w", "ana", "tui", replay=False, slot="chat:1")

    assert link.client == "c3"
    assert daemon_.calls[0] == (
        "session.hello",
        {"name": "ana", "kind": "tui", "at": tmp_path},
    )
    assert daemon_.calls[1] == (
        "epic.attach",
        {"workspace": "/w", "slot": "chat:1", "replay": False},
    )


def test_reached_names_a_frontend_nobody_named(
    daemon_: _Daemon, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_NAME", "dana")
    reached(tmp_path, "/w", kind="sdk")

    assert daemon_.calls[0][1]["name"] == "dana@sdk"


def test_reached_turns_a_refused_attach_into_an_os_error(
    daemon_: _Daemon, tmp_path: Path
) -> None:
    from hmz.rpc import RpcError

    daemon_.answers["epic.attach"] = RpcError(409, "This chat has folded away.")
    with pytest.raises(OSError, match="folded away"):
        reached(tmp_path, "/w")
    assert daemon_.closed.is_set()


def test_reached_hands_on_the_messages_of_its_own_subscription(
    daemon_: _Daemon, tmp_path: Path
) -> None:
    link = reached(tmp_path, "/w")
    daemon_.tells("s9", {"type": "printed", "text": "not mine"})
    daemon_.tells("s1", {"type": "printed", "text": "mine"})
    daemon_.tells("s1", {"type": "gone", "why": "let go"})

    assert [one.get("text") or one.get("why") for one in link] == ["mine", "let go"]
    with pytest.raises(Refused, match="let go"):
        link.say("hi")


def test_reached_calls_the_epic_with_its_sub_and_an_idem_for_a_write(
    daemon_: _Daemon, tmp_path: Path
) -> None:
    daemon_.answers["epic.say"] = {}
    daemon_.answers["epic.status"] = {"state": "idle"}
    link = reached(tmp_path, "/w")

    assert link.say("hi") == {"ok": True}
    assert link.asked({"do": "status"}) == {"ok": True, "state": "idle"}
    said = dict(daemon_.calls)
    assert said["epic.say"]["sub"] == "s1"
    assert said["epic.say"]["idem"]
    assert "idem" not in said["epic.status"]


def test_reached_raises_a_refusal_in_the_hosts_words(
    daemon_: _Daemon, tmp_path: Path
) -> None:
    from hmz.rpc import RpcError

    daemon_.answers["epic.say"] = RpcError(409, "no flow is running to say it to")
    link = reached(tmp_path, "/w")
    with pytest.raises(Refused, match="no flow is running"):
        link.say("hi")


def test_reached_gives_up_waiting_and_says_so(daemon_: _Daemon, tmp_path: Path) -> None:
    daemon_.answers["epic.stop"] = TimeoutError
    link = reached(tmp_path, "/w")
    with pytest.raises(TimeoutError, match=r"no answer to 'stop' in 1s"):
        link.asked({"do": "stop"}, seconds=1)


def test_reached_says_the_host_went_away_when_its_session_ends(
    daemon_: _Daemon, tmp_path: Path
) -> None:
    link = reached(tmp_path, "/w")
    daemon_.close()

    assert list(link) == [{"type": "gone", "why": "the host went away"}]


class _Afar:
    """Another machine's interface, as `Remotes` reaches it: what it was asked, what it says."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str, dict[str, Any] | None]] = []

    def followed(
        self, name: str, path: str, going: threading.Event
    ) -> Iterable[tuple[str, Any]]:
        del going
        self.asked.append((name, path, None))
        yield "hello", {"epoch": "e", "me": "c7"}
        yield "record", {"type": "started", "seq": 1, "task": "hi"}
        yield "standing", {"type": "run", "state": "running"}
        yield "gone", {"why": "closing"}

    def asked_of(self, name: str, path: str, body: dict[str, Any] | None = None) -> Any:
        self.asked.append((name, path, body))
        if body and body.get("text") == "no":
            from hmz.runtime.doing.daemons import Unreached

            raise Unreached("refused there", status=409)
        return {"ok": True, "run": 3}


def test_a_remote_link_asks_that_interface_and_is_told_its_stream() -> None:
    afar = _Afar()
    remotes = mock.Mock(followed=afar.followed, asked=afar.asked_of)

    link = remote(remotes, "box", "/w s")
    told = list(link)

    assert link.client == "c7"
    assert [one["type"] for one in told] == ["started", "run", "gone"]
    assert told[-1]["why"] == "closing"
    assert link.say("hello")["run"] == 3
    with pytest.raises(Refused, match="refused there"):
        link.say("no")
    assert afar.asked[0] == ("box", "/api/held/stream?workspace=/w%20s", None)
    assert afar.asked[1] == (
        "box",
        "/api/held/say",
        {"text": "hello", "to": "", "workspace": "/w s", "slot": ""},
    )
