"""Runs started, read, answered and stopped through a host, by frontends of their own.

The host is forked for real by `hmz.daemon.host()`; the frontends are `hmz.daemon.Link`s here
and programs written against `hmz.sdk` in processes of their own. The flows drive no agent:
whoever is outside the run is a frontend, and the rest is the workspace's own files.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.daemon import linked
from hmz.runtime import Hmz, Refused
from tests.integration.doubles_daemon import (
    ASKS,
    PATIENCE,
    SAYS,
    WAITS,
    Heard,
    answering,
    hosting,
    project,
    replayed,
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
    for name, source in (("asks", ASKS), ("says", SAYS), ("waits", WAITS)):
        written(at, name, source)
    with hosting():
        yield at


@pytest.fixture
def held(workspace: Path) -> Iterator[daemon.Daemon]:
    one = daemon.host()
    try:
        yield one
    finally:
        (workspace / "go").write_text("")


def test_frontends_of_their_own_each_answer_for_the_role_they_claimed(
    held: daemon.Daemon, workspace: Path
) -> None:
    heard = Heard()
    with answering("planner", "reviewer") as frontends:
        with held.link(name="starter") as link:
            link.heard(heard)
            assert link.start("./asks", "the parser", budget={"cost": 1})["run"] == 1
            assert until(lambda: heard.of("ended"))
        assert heard.of("ended")[0]["how"] == "done", heard.of("ended")[0]["why"]
        for one in frontends:
            assert one.wait(PATIENCE) == 0

    assert json.loads((workspace / "result.json").read_text()) == {
        "plan": "planner says yes",
        "review": "reviewer says yes",
    }
    assert [(one["role"], one["by"]) for one in heard.of("answered")] == [
        ("planner", "planner"),
        ("reviewer", "reviewer"),
    ]
    (started,) = heard.of("started")
    assert (started["by"], started["outworlders"]) == (
        "starter",
        ["planner", "reviewer"],
    )


def test_every_frontend_is_told_the_same_run_in_the_same_order(
    held: daemon.Daemon, workspace: Path
) -> None:
    heard = [Heard(), Heard()]
    links = [held.link(name="one"), held.link(name="two")]
    try:
        for link, seen in zip(links, heard, strict=True):
            link.heard(seen)
        links[0].start("./says", "a run", budget={"cost": 1})
        (workspace / "go").write_text("")
        assert until(lambda: all(seen.of("ended") for seen in heard))
    finally:
        for link in links:
            link.close()

    def run(seen: Heard) -> list[str]:
        kinds = ("started", "printed", "ended")
        return [one["type"] for one in seen.messages if one["type"] in kinds]

    assert run(heard[0]) == run(heard[1]) == ["started", "printed", "ended"]
    assert heard[1].of("printed")[0]["text"] == "a run printed"


def test_a_frontend_arriving_late_is_told_the_run_so_far_unless_it_asks_not_to(
    held: daemon.Daemon, workspace: Path
) -> None:
    with held.link(name="starter") as link:
        link.start("./says", "early", budget={"cost": 1})
        with held.link(name="late") as late:
            told = replayed(late)
        with held.link(name="fresh", replay=False) as fresh:
            fresh_told = replayed(fresh)
        (workspace / "go").write_text("")

    assert told[0] == fresh_told[0] == "welcome"
    assert "started" in told
    assert "started" not in fresh_told


def test_a_run_that_ended_with_nobody_there_waits_for_somebody_to_read_it(
    held: daemon.Daemon, workspace: Path
) -> None:
    with held.link(name="starter") as link:
        link.start("./says", "unread", budget={"cost": 1})
    (workspace / "go").write_text("")
    assert until(lambda: held.status()["state"] != "running")

    assert held.alive
    with held.link(name="late") as late:
        assert "ended" in replayed(late)
    # That was who it was held for: nobody is left to hold it for.
    assert until(lambda: not held.alive)


def test_stopping_a_run_unwinds_it_and_the_host_stays(held: daemon.Daemon) -> None:
    heard = Heard()
    with held.link(name="starter") as link:
        link.heard(heard)
        link.start("./waits", "forever", budget={"cost": 1})
        assert held.status()["state"] == "running"
        assert held.status()["flow"] == "./waits"

        assert link.stop()["ok"]

        assert until(lambda: heard.of("ended"))
        assert heard.of("stopping")[0]["by"] == "starter"
        with pytest.raises(Refused, match="nothing to stop"):
            link.stop()
        assert held.alive


def test_a_second_run_while_one_is_running_is_refused(held: daemon.Daemon) -> None:
    with held.link(name="starter") as link:
        link.start("./waits", "forever", budget={"cost": 1})
        with pytest.raises(Refused, match="already running"):
            link.start("./says", "too", budget={"cost": 1})
        link.stop()


def test_a_refusal_reads_the_same_through_the_daemon_as_in_this_process(
    held: daemon.Daemon,
) -> None:
    host = Hmz().host()
    here = linked(host, name="here")
    try:
        with held.link(name="there") as there:
            for request in ({"do": "nope"}, {"do": "start", "flow": "./missing"}):
                with pytest.raises(Refused) as far:
                    there.asked(request)
                with pytest.raises(Refused) as near:
                    here.asked(request)
                assert str(far.value) == str(near.value)
    finally:
        here.close()
        host.close()
