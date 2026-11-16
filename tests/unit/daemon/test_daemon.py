"""`hmz.daemon`: which workspaces' runs are held, and asking the daemon about them."""

from __future__ import annotations

import errno
import os
import signal
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

import hmz.daemon
import hmz.daemon.link
import hmz.runtime
from hmz import daemon
from hmz.daemon import Daemon, Link, linked, where
from hmz.rpc import RpcError

if TYPE_CHECKING:
    from collections.abc import Callable

#: The protocol version every daemon here speaks.
PROTOCOL = "3.0.0"


def test_all_names_what_the_package_offers() -> None:
    assert set(daemon.__all__) == {
        "Daemon",
        "Hmz",
        "Host",
        "Link",
        "Older",
        "Refused",
        "attach",
        "daemons",
        "host",
        "linked",
        "running",
        "start",
    }
    for name in daemon.__all__:
        assert getattr(daemon, name) is not None
    assert Link is hmz.daemon.link.Link
    assert linked is hmz.daemon.link.linked


@pytest.mark.parametrize("name", ["Hmz", "Host", "Refused"])
def test_the_runtime_is_handed_through_as_itself(name: str) -> None:
    assert getattr(daemon, name) is getattr(hmz.runtime, name)


def test_a_name_nobody_has_is_an_attribute_error() -> None:
    with pytest.raises(AttributeError, match="no attribute 'Nothing'"):
        _ = daemon.Nothing


@pytest.fixture
def at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The daemon's directory, under the test's own."""
    monkeypatch.setattr(where, "at", lambda: tmp_path)
    return tmp_path


class _Peer:
    """A session with the daemon: each call answered by a function of the test's."""

    def __init__(self, answers: Callable[[str, dict[str, Any]], Any]) -> None:
        self._answers = answers

    def call(self, method: str, params: dict[str, Any], timeout: float) -> Any:
        del timeout
        said = self._answers(method, params)
        if isinstance(said, BaseException):
            raise said
        return said

    def close(self) -> None:
        pass


@pytest.fixture
def answering(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Callable[[str, dict[str, Any]], Any]]:
    """Has every session with the daemon answered by the first of the functions given.

    No function at all is nothing listening.
    """
    answers: list[Callable[[str, dict[str, Any]], Any]] = []

    def dialed(at: Path, *_: object, **__: object) -> tuple[_Peer, dict[str, Any]]:
        del at
        if not answers:
            raise ConnectionRefusedError(errno.ECONNREFUSED, "refused")
        return _Peer(answers[0]), {}

    def connects(at: Path, seconds: float | None = None) -> mock.Mock:
        del at, seconds
        if not answers:
            raise ConnectionRefusedError(errno.ECONNREFUSED, "refused")
        return mock.Mock()

    monkeypatch.setattr(hmz.daemon.link, "dialed", dialed)
    monkeypatch.setattr(where, "connects", connects)
    return answers


def _record(at: Path, **said: Any) -> None:
    where.wrote(
        at,
        {"pid": os.getpid(), "started": "s", "kind": "daemon", "protocol": PROTOCOL}
        | said,
    )


def _lists(*held: dict[str, Any]) -> Callable[[str, dict[str, Any]], Any]:
    def answers(method: str, params: dict[str, Any]) -> Any:
        del params
        if method == "hosts.list":
            return {"held": list(held)}
        return RpcError(404, "not this")

    return answers


def test_nothing_is_running_where_nothing_was_written(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    answering.append(_lists())
    assert daemon.running(at) is None
    assert daemon.daemons() == []


def test_nothing_is_running_where_nothing_is_listening(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    _record(at)
    assert daemon.running(at) is None
    assert daemon.daemons() == []
    del answering


def test_nothing_is_running_where_the_directory_is_somebody_elses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuses() -> Path:
        raise PermissionError("somebody else's")

    monkeypatch.setattr(where, "at", refuses)
    assert daemon.running("/w") is None
    assert daemon.daemons() == []


def test_running_finds_the_host_of_a_workspace(
    at: Path,
    tmp_path: Path,
    answering: list[Callable[[str, dict[str, Any]], Any]],
) -> None:
    _record(at)
    workspace = where.workspace(tmp_path)
    answering.append(
        _lists(
            {"pid": os.getpid(), "workspace": workspace, "started": "t2", "slot": ""},
            {"pid": os.getpid(), "workspace": "/elsewhere", "started": "t1"},
        )
    )
    found = daemon.running(tmp_path)
    assert found == Daemon(
        at=at, workspace=workspace, pid=os.getpid(), started="t2", protocol=PROTOCOL
    )
    assert found is not None
    assert found.alive
    assert daemon.running("/nowhere") is None
    assert [one.started for one in daemon.daemons()] == ["t1", "t2"]


def test_hosts_whose_process_has_gone_are_left_out(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    _record(at)
    answering.append(
        _lists(
            {"pid": 0, "workspace": "/a", "started": "1"},
            {"pid": "12", "workspace": "/b", "started": "2"},
            {"workspace": "/c"},
        )
    )
    assert daemon.daemons() == []


@pytest.mark.parametrize("protocol", [2, "2.0.0", None])
def test_a_daemon_of_another_protocol_is_named_as_it_is(
    at: Path,
    tmp_path: Path,
    answering: list[Callable[[str, dict[str, Any]], Any]],
    protocol: object,
) -> None:
    _record(at, protocol=protocol, started="then")
    answering.append(_lists())
    said = protocol if isinstance(protocol, str) else ""
    assert daemon.running(tmp_path) == Daemon(
        at=at,
        workspace=where.workspace(tmp_path),
        pid=os.getpid(),
        started="then",
        protocol=said,
    )
    assert daemon.daemons() == [
        Daemon(at=at, workspace="", pid=os.getpid(), started="then", protocol=said)
    ]


def test_host_asks_the_daemon_to_open_the_host(
    at: Path,
    tmp_path: Path,
    answering: list[Callable[[str, dict[str, Any]], Any]],
) -> None:
    _record(at)
    workspace = where.workspace(tmp_path)
    asked: list[tuple[str, dict[str, Any]]] = []

    def opens(method: str, params: dict[str, Any]) -> Any:
        asked.append((method, params))
        return {
            "pid": 7,
            "workspace": workspace,
            "started": "t",
            "kind": "host",
            "protocol": PROTOCOL,
            "slot": "chat:1",
        }

    answering.append(opens)
    found = daemon.host(tmp_path, slot="chat:1")
    assert found == Daemon(
        at=at, workspace=workspace, pid=7, started="t", protocol=PROTOCOL, slot="chat:1"
    )
    assert asked == [("hosts.open", {"workspace": workspace, "slot": "chat:1"})]


def test_host_refuses_a_daemon_of_another_protocol(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    _record(at, protocol="2.0.0")
    answering.append(_lists())
    with pytest.raises(OSError, match="older Humanize") as raised:
        daemon.host(at)
    assert raised.value.errno == errno.EADDRINUSE


@pytest.mark.parametrize(
    ("workspace", "said"), [("/w", "in /w"), ("", "on this machine")]
)
def test_older_says_where_the_runs_are_and_what_to_do(
    workspace: str, said: str
) -> None:
    found = Daemon(at=Path("/d"), workspace=workspace, pid=42, started="")
    assert daemon.older(found) == (
        f"the runs {said} are held by an older Humanize (pid 42); "
        "stop it with that version"
    )


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The daemon as `attach` reaches it: started, attached to, and waited on."""
    held = mock.Mock()
    monkeypatch.setattr(daemon, "start", held.start)
    monkeypatch.setattr(hmz.daemon.link, "reached", held.reached)
    monkeypatch.setattr(time, "sleep", held.sleep)
    return held


def test_attach_starts_the_daemon_and_attaches_through_it(
    reached: mock.Mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(where, "at", lambda: tmp_path)
    assert daemon.attach("web", "browser", workspace=tmp_path) is (
        reached.reached.return_value
    )
    reached.reached.assert_called_once_with(
        tmp_path, where.workspace(tmp_path), "browser", "web", slot=""
    )


def test_attach_refuses_runs_held_by_an_older_humanize(reached: mock.Mock) -> None:
    reached.start.side_effect = OSError(errno.EADDRINUSE, "held by an older Humanize")
    with pytest.raises(daemon.Older, match="older Humanize"):
        daemon.attach("tui")
    reached.reached.assert_not_called()


def test_attach_reaches_again_for_a_host_found_going(reached: mock.Mock) -> None:
    reached.reached.side_effect = [OSError("gone"), "link"]
    assert daemon.attach("tui") == "link"
    assert reached.sleep.call_count == 1


def test_attach_gives_up_on_runs_that_cannot_be_held_apart(reached: mock.Mock) -> None:
    reached.reached.side_effect = OSError("no fork")
    with pytest.raises(OSError, match="no fork"):
        daemon.attach("tui")
    assert reached.reached.call_count == 3


def _held(at: Path, pid: int = 4242, slot: str = "") -> Daemon:
    return Daemon(
        at=at, workspace="/w", pid=pid, started="t", protocol=PROTOCOL, slot=slot
    )


def test_a_daemon_is_a_frozen_value() -> None:
    one = _held(Path("/d"))
    assert one == _held(Path("/d"))
    assert Daemon(at=Path("/d"), workspace="", pid=1, started="").protocol == ""
    with pytest.raises(AttributeError):
        one.pid = 1  # pyright: ignore[reportAttributeAccessIssue]


def test_asked_calls_the_hosts_method_naming_the_host(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    seen: list[tuple[str, dict[str, Any]]] = []
    answering.append(lambda method, params: seen.append((method, params)) or {"n": 1})
    assert _held(at, slot="chat:2").asked({"do": "status"}) == {"n": 1}
    assert seen == [("hosts.status", {"workspace": "/w", "slot": "chat:2"})]


def test_asked_is_nothing_where_nobody_answers(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    assert _held(at).asked({"do": "x"}) == {}
    answering.append(lambda method, params: RpcError(409, "refused"))
    assert _held(at).asked({"do": "x"}) == {}


def test_status_of_a_host_that_will_not_answer_is_what_is_known_of_it(
    at: Path, answering: list[Callable[[str, dict[str, Any]], Any]]
) -> None:
    del answering
    assert _held(at).status() == {
        "pid": 4242,
        "workspace": "/w",
        "started": "t",
        "kind": "host",
        "protocol": PROTOCOL,
        "attached": 0,
        "flows": [],
        "calls": [],
    }


@pytest.mark.parametrize(
    ("answer", "count"), [({"let_go": 3}, 3), ({"let_go": "3"}, 0), ({}, 0)]
)
def test_detach_says_how_many_were_let_go_of(
    at: Path,
    answering: list[Callable[[str, dict[str, Any]], Any]],
    answer: dict[str, Any],
    count: int,
) -> None:
    answering.append(lambda method, params: answer)
    assert _held(at).detach() == count


@pytest.fixture
def lives(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """What `where.alive` says each time it is asked, and then that it has gone."""
    said: list[bool] = []

    def alive(pid: int) -> bool:
        del pid
        return said.pop(0) if said else False

    monkeypatch.setattr(where, "alive", alive)
    monkeypatch.setattr(time, "sleep", mock.Mock())
    return said


def test_stop_waits_for_the_host_to_go(
    at: Path,
    answering: list[Callable[[str, dict[str, Any]], Any]],
    lives: list[bool],
) -> None:
    answering.append(lambda method, params: {} if method == "hosts.stop" else None)
    lives.extend([True, True])
    assert _held(at).stop() is True
    assert lives == []


def test_stop_that_cannot_be_asked_says_whether_it_has_gone(
    at: Path,
    answering: list[Callable[[str, dict[str, Any]], Any]],
    lives: list[bool],
) -> None:
    lives.append(True)
    assert _held(at).stop() is False
    assert _held(at).stop() is True
    del answering


def test_kill_terminates_and_then_kills(
    monkeypatch: pytest.MonkeyPatch, lives: list[bool]
) -> None:
    signalled = mock.Mock()
    monkeypatch.setattr(os, "kill", signalled)
    lives.extend([True, True])
    assert _held(Path("/d")).kill(seconds=0) is True
    assert signalled.call_args_list == [
        mock.call(4242, signal.SIGTERM),
        mock.call(4242, signal.SIGKILL),
    ]


def test_link_reaches_the_runs_through_the_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reaches = mock.Mock(return_value="link")
    monkeypatch.setattr(hmz.daemon.link, "reached", reaches)
    assert _held(Path("/d")).link("me", "tui", replay=False) == "link"
    reaches.assert_called_once_with(
        Path("/d"), "/w", "me", "tui", replay=False, slot=""
    )
