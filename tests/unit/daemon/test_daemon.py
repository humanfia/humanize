"""`hmz.daemon`: which workspaces' runs are held, and asking them about themselves."""

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
from hmz.daemon.proto import CONTROL, PROTOCOL, spoken
from tests.unit.daemon.wire_u1 import Wire

if TYPE_CHECKING:
    from collections.abc import Callable


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


@pytest.fixture
def answering(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Callable[[dict[str, Any]], dict[str, Any]]]:
    """Has every connection to the daemon answered by the first of the functions given.

    No function at all is nothing listening.
    """
    answers: list[Callable[[dict[str, Any]], dict[str, Any]]] = []
    asked: list[dict[str, Any]] = []

    def connects(at: Path, seconds: float | None = None) -> Wire:
        del at, seconds
        if not answers:
            raise ConnectionRefusedError(errno.ECONNREFUSED, "refused")

        def replies(kind: bytes, said: dict[str, Any]) -> list[bytes]:
            assert kind == CONTROL
            asked.append(said)
            return [spoken(CONTROL, answers[0](said))]

        return Wire(replies)

    monkeypatch.setattr(where, "connects", connects)
    return answers


def _record(at: Path, **said: Any) -> None:
    where.wrote(
        at,
        {"pid": os.getpid(), "started": "s", "kind": "daemon", "protocol": PROTOCOL}
        | said,
    )


def _lists(*held: dict[str, Any]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def answers(said: dict[str, Any]) -> dict[str, Any]:
        if said.get("do") == "list":
            return {"ok": True, "held": list(held)}
        return {"ok": False}

    return answers


def test_nothing_is_running_where_nothing_was_written(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    answering.append(_lists())
    assert daemon.running(at) is None
    assert daemon.daemons() == []


def test_nothing_is_running_where_nothing_is_listening(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
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
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
) -> None:
    _record(at)
    workspace = where.workspace(tmp_path)
    answering.append(
        _lists(
            {"pid": os.getpid(), "workspace": workspace, "started": "t2"},
            {"pid": os.getpid(), "workspace": "/elsewhere", "started": "t1"},
        )
    )
    found = daemon.running(tmp_path)
    assert found is not None
    assert found == Daemon(
        at=at, workspace=workspace, pid=os.getpid(), started="t2", protocol=PROTOCOL
    )
    assert found.alive
    assert daemon.running("/nowhere") is None
    assert [one.started for one in daemon.daemons()] == ["t1", "t2"]


def test_hosts_whose_process_has_gone_are_left_out(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
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


def test_a_list_that_is_not_one_is_no_hosts(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    _record(at)
    answering.append(lambda said: {"ok": True, "held": "nope"})
    assert daemon.daemons() == []


def test_a_daemon_of_another_protocol_is_named_as_it_is(
    at: Path,
    tmp_path: Path,
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
) -> None:
    _record(at, protocol=1, started="then")
    answering.append(_lists())
    found = daemon.running(tmp_path)
    assert found == Daemon(
        at=at,
        workspace=where.workspace(tmp_path),
        pid=os.getpid(),
        started="then",
        protocol=1,
    )
    assert daemon.daemons() == [
        Daemon(at=at, workspace="", pid=os.getpid(), started="then", protocol=1)
    ]


def test_host_hands_back_the_host_already_there(
    at: Path,
    tmp_path: Path,
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
) -> None:
    _record(at)
    workspace = where.workspace(tmp_path)
    answering.append(
        _lists({"pid": os.getpid(), "workspace": workspace, "started": "t"})
    )
    found = daemon.host(tmp_path)
    assert found.workspace == workspace
    assert found.protocol == PROTOCOL


def test_host_refuses_a_daemon_of_another_protocol(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    _record(at, protocol=1)
    answering.append(_lists())
    with pytest.raises(OSError, match="older humanize") as raised:
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
        f"the runs {said} are held by an older humanize (pid 42); "
        "stop it with that version"
    )


@pytest.fixture
def reached(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """The runs held here as `attach` reaches them: found, started, and waited on."""
    held = mock.Mock()
    held.running.return_value = None
    for name in ("running", "host"):
        monkeypatch.setattr(daemon, name, getattr(held, name))
    monkeypatch.setattr(time, "sleep", held.sleep)
    return held


def test_attach_links_to_the_host_already_there(reached: mock.Mock) -> None:
    found = mock.Mock(protocol=PROTOCOL)
    reached.running.return_value = found
    assert daemon.attach("web", "browser") is found.link.return_value
    found.link.assert_called_once_with(name="browser", kind="web")
    reached.host.assert_not_called()


def test_attach_starts_a_host_where_none_is(reached: mock.Mock) -> None:
    assert daemon.attach("tui") is reached.host.return_value.link.return_value
    reached.host.return_value.link.assert_called_once_with(name="", kind="tui")


def test_attach_refuses_runs_held_by_an_older_humanize(reached: mock.Mock) -> None:
    reached.running.return_value = Daemon(
        at=Path("/d"), workspace="/w", pid=42, started="", protocol=PROTOCOL - 1
    )
    with pytest.raises(daemon.Older, match="older humanize"):
        daemon.attach("tui")
    reached.host.assert_not_called()


def test_attach_reaches_again_for_a_host_found_going(reached: mock.Mock) -> None:
    reached.host.return_value.link.side_effect = [OSError("gone"), "link"]
    assert daemon.attach("tui") == "link"
    assert reached.sleep.call_count == 1


def test_attach_gives_up_on_runs_that_cannot_be_held_apart(reached: mock.Mock) -> None:
    reached.host.side_effect = OSError("no fork")
    with pytest.raises(OSError, match="no fork"):
        daemon.attach("tui")
    assert reached.host.call_count == 3


def _held(at: Path, pid: int = 4242) -> Daemon:
    return Daemon(at=at, workspace="/w", pid=pid, started="t", protocol=PROTOCOL)


def test_a_daemon_is_a_frozen_value() -> None:
    one = _held(Path("/d"))
    assert one == _held(Path("/d"))
    assert one.protocol == PROTOCOL
    assert Daemon(at=Path("/d"), workspace="", pid=1, started="").protocol == 0
    with pytest.raises(AttributeError):
        one.pid = 1  # pyright: ignore[reportAttributeAccessIssue]


def test_asked_names_the_workspace_and_returns_the_answer(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    seen: list[dict[str, Any]] = []
    answering.append(lambda said: seen.append(said) or {"ok": True, "n": 1})
    assert _held(at).asked({"do": "x"}) == {"ok": True, "n": 1}
    assert seen == [{"do": "x", "workspace": "/w"}]


def test_asked_is_nothing_where_nobody_answers(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    assert _held(at).asked({"do": "x"}) == {}
    del answering


def test_status_is_what_the_runs_say(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    answering.append(lambda said: {"ok": True, "attached": 2, "flows": ["f"]})
    assert _held(at).status() == {"ok": True, "attached": 2, "flows": ["f"]}


def test_status_of_runs_that_will_not_answer_is_what_is_written_down(
    at: Path, answering: list[Callable[[dict[str, Any]], dict[str, Any]]]
) -> None:
    answering.append(lambda said: {"ok": False})
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
    ("answer", "count"),
    [({"ok": True, "let go": 3}, 3), ({"ok": True, "let go": "3"}, 0), ({}, 0)],
)
def test_detach_says_how_many_were_let_go_of(
    at: Path,
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
    answer: dict[str, Any],
    count: int,
) -> None:
    answering.append(lambda said: answer)
    assert _held(at).detach() == count


@pytest.fixture
def lives(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """What `where.alive` says each time it is asked, and then that it has gone."""
    said: list[bool] = []

    def alive(pid: int) -> bool:
        del pid
        return said.pop(0) if said else False

    def sleep(seconds: float) -> None:
        del seconds

    monkeypatch.setattr(where, "alive", alive)
    monkeypatch.setattr(time, "sleep", sleep)
    return said


def test_stop_waits_for_the_host_to_go(
    at: Path,
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
    lives: list[bool],
) -> None:
    answering.append(lambda said: {"ok": said["do"] == "stop"})
    lives.extend([True, True])
    assert _held(at).stop() is True
    assert lives == []


def test_stop_that_cannot_be_asked_says_whether_it_has_gone(
    at: Path,
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
    lives: list[bool],
) -> None:
    lives.append(True)
    assert _held(at).stop() is False
    assert _held(at).stop() is True
    del answering


def test_stop_that_outlasts_its_seconds_says_so(
    at: Path,
    answering: list[Callable[[dict[str, Any]], dict[str, Any]]],
    lives: list[bool],
) -> None:
    answering.append(lambda said: {"ok": True})
    lives.append(True)
    assert _held(at).stop(seconds=0) is False


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


def test_kill_of_a_host_that_goes_at_the_terminate_kills_nothing(
    monkeypatch: pytest.MonkeyPatch, lives: list[bool]
) -> None:
    signalled = mock.Mock(side_effect=ProcessLookupError)
    monkeypatch.setattr(os, "kill", signalled)
    assert _held(Path("/d")).kill() is True
    signalled.assert_called_once_with(4242, signal.SIGTERM)
    del lives


def test_link_reaches_the_runs_through_the_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reaches = mock.Mock(return_value="link")
    monkeypatch.setattr(hmz.daemon.link, "reached", reaches)
    assert _held(Path("/d")).link("me", "tui", replay=False) == "link"
    reaches.assert_called_once_with(Path("/d"), "/w", "me", "tui", replay=False)
