"""A workspace's runs held by a host of their own, reached through the machine's one daemon.

`hmz.daemon.host()` forks for real: a daemon per machine, a host per workspace, each found
again by `running()`, `daemons()` and `hmz.sdk.Daemons`, and each gone once nothing is left
for it to hold.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.daemon.proto import PROTOCOL
from hmz.sdk import Daemons
from tests.integration.doubles_daemon import (
    SAYS,
    WAITS,
    Heard,
    hosting,
    project,
    until,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(90),
    pytest.mark.filterwarnings("ignore:.*use of fork.*:DeprecationWarning"),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    with hosting():
        yield at


@pytest.fixture
def held(workspace: Path) -> daemon.Daemon:
    return daemon.host()


def test_nothing_is_held_before_a_host_is_asked_for(workspace: Path) -> None:
    assert daemon.running() is None
    assert daemon.daemons() == []
    assert Daemons().here(workspace) is None
    assert Daemons().all() == []


def test_a_host_is_found_again_rather_than_started_twice(
    held: daemon.Daemon, workspace: Path
) -> None:
    assert held.alive
    assert held.workspace == where.workspace(workspace)
    assert held.protocol == PROTOCOL
    found = daemon.running()
    assert found is not None
    assert found.pid == held.pid
    assert daemon.host().pid == held.pid
    assert Daemons().host().pid == held.pid
    assert [one.pid for one in Daemons().all()] == [held.pid]
    # The machine's daemon is a process apart from the host it routes to.
    assert where.held(where.at())["pid"] not in (held.pid, 0)


def test_status_says_who_is_reading_and_that_nothing_runs(held: daemon.Daemon) -> None:
    status = held.status()
    assert (status["kind"], status["attached"], status["state"]) == ("host", 0, "idle")
    assert status["pid"] == held.pid

    with held.link(name="watcher", kind="cli") as link:
        assert link.client
        status = held.status()
        assert status["attached"] == 1
        assert [(one["name"], one["kind"]) for one in status["clients"]] == [
            ("watcher", "cli")
        ]


def test_detach_lets_every_frontend_go_and_keeps_the_run_going(
    held: daemon.Daemon, workspace: Path
) -> None:
    written(workspace, "waits", WAITS)
    heard = Heard()
    link = held.link(name="one")
    link.heard(heard)
    try:
        link.start("./waits", "forever", budget={"cost": 1})
        assert held.detach() == 1
        assert until(lambda: heard.of("gone"))
        assert held.status()["state"] == "running"
        assert held.alive
    finally:
        link.close()


def test_a_host_nobody_reads_and_nothing_runs_in_goes(held: daemon.Daemon) -> None:
    with held.link(name="passing"):
        assert held.status()["attached"] == 1

    assert until(lambda: not held.alive)
    assert daemon.running() is None


def test_stopping_the_host_tells_every_frontend_why(held: daemon.Daemon) -> None:
    heard = Heard()
    link = held.link(name="watching")
    link.heard(heard)
    try:
        assert held.stop()
        assert not held.alive
        assert until(
            lambda: {"type": "gone", "why": "the host was closed"} in heard.of("gone")
        )
    finally:
        link.close()


def test_killing_the_host_leaves_nothing_held(held: daemon.Daemon) -> None:
    assert held.kill()
    assert daemon.running() is None
    # Once its last host has gone, the machine's daemon goes too.
    assert until(lambda: not where.alive(int(where.held(where.at()).get("pid") or 0)))


def test_one_daemon_holds_every_workspace_and_each_run_writes_its_own_epic(
    workspace: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    for one in (workspace, other):
        written(one, "says", SAYS)
    first, second = daemon.host(workspace), daemon.host(other)
    machine = where.held(where.at())["pid"]
    assert len({first.pid, second.pid, machine}) == 3
    assert [one.workspace for one in daemon.daemons()] == [
        where.workspace(workspace),
        where.workspace(other),
    ]
    assert Daemons().here(other) == second

    heard = {"first": Heard(), "second": Heard()}
    links = [first.link(name="starter"), second.link(name="starter")]
    try:
        for link, (task, seen) in zip(links, heard.items(), strict=True):
            link.heard(seen)
            assert link.start("./says", task, budget={"cost": 1})["run"] == 1
        assert first.status()["state"] == second.status()["state"] == "running"
        for one in (workspace, other):
            (one / "go").write_text("")
        assert until(lambda: all(seen.of("ended") for seen in heard.values()))
    finally:
        for link in links:
            link.close()

    for task, seen in heard.items():
        assert [one["text"] for one in seen.of("printed")] == [f"{task} printed"]
    from hmz import home

    def logs() -> list[str]:
        return sorted(one.read_text() for one in (home() / "epics").rglob("host.log"))

    assert until(lambda: len(logs()) == 2)
    assert logs() == [
        "first said straight to a descriptor\n",
        "second said straight to a descriptor\n",
    ]
