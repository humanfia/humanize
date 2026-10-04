"""A workspace's runs hosted where a terminal closing cannot end them, with frontends of their own.

The whole of it as it really works: `daemon.host()` forking a process that holds the runs, and
frontends that are processes of their own -- a program written against the SDK apiece -- each
answering for the role it claimed. What the carrying does with each thing that can arrive is
`tests/integration/daemon/test_carrying.py`, which drives it in this process.

Integration rather than system: a fork and a socket on this machine are things every runner
has, and what the frontends run is a flow that drives no agent at all.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli, daemon, home
from hmz.daemon import where
from hmz.daemon.proto import PROTOCOL
from hmz.sdk import Daemons
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from tests.machines.fixtures import Standin

#: How long a test waits for something another process is doing.
PATIENCE = 30.0

#: Two people outside the run, asked one after the other, and what each said kept.
ASKS = """
import asyncio
import json
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="asks")
async def asks(task, *, agents, envs, params, ctx):
    here = envs["workspace"]
    while not Path("go").exists():
        await asyncio.sleep(0.02)
    planner = await agents["planner"].spawn(env=here)
    reviewer = await agents["reviewer"].spawn(env=here)
    plan = await agents["planner"].run(f"what is the plan for {task}?", session=planner)
    review = await agents["reviewer"].run(f"is {plan!r} good?", session=reviewer)
    print(f"planned {plan} and reviewed {review}")
    Path("result.json").write_text(json.dumps({"plan": plan, "review": review}))
"""

#: A frontend in a process of its own: claims one role, and answers what it asks.
ANSWERS = """
import sys

from hmz.sdk import Daemons

role = sys.argv[1]
with Daemons().here().link(name=role, replay=False) as link:
    link.claim(role)
    print("claimed", flush=True)
    for said in link:
        if said["type"] == "pending":
            for one in said["pending"]:
                if one["role"] == role and one["owner"] == link.client:
                    link.answer(one["question"], f"{role} says yes")
        if said["type"] == "ended":
            break
"""


def until(what: Callable[[], object], seconds: float = PATIENCE) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.05)
    return bool(what())


@pytest.fixture
def hosted(workspace: Path) -> Iterator[daemon.Daemon]:
    """This workspace's runs, hosted, and gone again however the test ended."""
    written(workspace, "asks", ASKS)
    one = daemon.host()
    try:
        yield one
    finally:
        (workspace / "go").write_text("")
        if one.alive:
            one.kill()


def _answering(role: str) -> subprocess.Popen[str]:
    """A frontend of its own for one role, once it holds the role."""
    process = subprocess.Popen(
        [sys.executable, "-c", ANSWERS, role],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "claimed", process.stderr
    return process


@pytest.mark.timeout(90)
def test_runs_are_hosted_apart_and_found_again(hosted: daemon.Daemon) -> None:
    found = daemon.running()

    assert found is not None
    assert (found.pid, found.protocol) == (hosted.pid, PROTOCOL)
    # Found rather than started again, however it is asked for.
    assert daemon.host().pid == hosted.pid
    assert Daemons().host().pid == hosted.pid
    status = hosted.status()
    assert (status["kind"], status["attached"], status["state"]) == ("host", 0, "idle")


@pytest.mark.timeout(90)
def test_frontends_of_their_own_each_answer_for_the_role_they_claimed(
    hosted: daemon.Daemon, workspace: Path
) -> None:
    frontends = [_answering(role) for role in ("planner", "reviewer")]
    seen: list[dict[str, Any]] = []
    with hosted.link(name="starter") as link:
        link.heard(seen.append)
        assert link.start("asks", "the parser", budget={"cost": 1})["run"] == 1
        (workspace / "go").write_text("")

        assert until(lambda: any(one["type"] == "ended" for one in list(seen)))
    for one in frontends:
        assert one.wait(PATIENCE) == 0, one.stderr

    assert (workspace / "result.json").read_text() == (
        '{"plan": "planner says yes", "review": "reviewer says yes"}'
    )
    answered = [(one["role"], one["by"]) for one in seen if one["type"] == "answered"]
    assert answered == [("planner", "planner"), ("reviewer", "reviewer")]
    # What the flow printed, which nobody reads the host's own terminal for.
    assert "planned planner says yes and reviewed reviewer says yes" in [
        one["text"] for one in seen if one["type"] == "printed"
    ]


@pytest.mark.timeout(90)
def test_a_host_nobody_is_reading_and_nothing_is_running_in_goes(
    hosted: daemon.Daemon,
) -> None:
    with hosted.link(name="passing"):
        assert hosted.status()["attached"] == 1

    assert until(lambda: not hosted.alive)
    assert daemon.running() is None


@pytest.mark.timeout(90)
def test_a_run_that_ended_with_nobody_there_waits_for_somebody_to_read_it(
    hosted: daemon.Daemon, workspace: Path
) -> None:
    with hosted.link(name="starter") as link:
        link.start("asks", "the parser", budget={"cost": 1})
        link.afk(on=True)
    (workspace / "go").write_text("")
    assert until((workspace / "result.json").exists)

    time.sleep(1.5)  # rounds enough for a host with nothing to hold to have gone
    assert hosted.alive
    with hosted.link(name="late") as late:
        replayed: list[str] = []
        for one in late:
            if one["type"] == "live":
                break
            replayed.append(one["type"])
    assert "ended" in replayed
    # And that was who it was waiting for: nobody is left to hold it for.
    assert until(lambda: not hosted.alive)


@pytest.mark.timeout(90)
def test_stopping_the_host_closes_it(hosted: daemon.Daemon) -> None:
    seen: list[dict[str, Any]] = []
    link = hosted.link(name="watching")
    link.heard(seen.append)

    assert hosted.stop()

    assert not hosted.alive
    assert until(
        lambda: any(
            one == {"type": "gone", "why": "the host was closed"} for one in list(seen)
        )
    )
    link.close()


@pytest.mark.timeout(90)
def test_killing_the_host_closes_it_first(hosted: daemon.Daemon) -> None:
    assert hosted.kill()
    assert daemon.running() is None


#: A run writing straight to a descriptor, once it is told to go: what a CLI it started would.
SAYS = """
import asyncio
import os
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="says")
async def says(task, *, agents, envs, params, ctx):
    while not Path("go").exists():
        await asyncio.sleep(0.02)
    os.write(2, f"{task} said straight to a descriptor\\n".encode())
"""


@pytest.mark.timeout(90)
def test_two_workspaces_are_held_at_once_by_the_one_daemon_of_the_machine(
    workspace: Path, tmp_path: Path
) -> None:
    """A host apiece, standing in its own workspace, and one socket every frontend reaches.

    And what each run's process wrote is in that run's epic, rather than in one log of the
    machine's that every workspace's runs write over one another in.
    """
    other = tmp_path / "other"
    other.mkdir()
    for one in (workspace, other):
        written(one, "says", SAYS)
    first, second = daemon.host(workspace), daemon.host(other)
    links: list[Any] = []
    try:
        machine = where.held(where.at())["pid"]
        assert first.pid != second.pid
        assert machine not in (first.pid, second.pid)
        assert [one.workspace for one in daemon.daemons()] == [
            where.workspace(workspace),
            where.workspace(other),
        ]
        seen: dict[str, list[dict[str, Any]]] = {}
        for one, task in ((first, "first"), (second, "second")):
            link = one.link(name="starter")
            links.append(link)
            seen[task] = []
            link.heard(seen[task].append)
            assert link.start("says", task, budget={"cost": 1})["run"] == 1

        assert first.status()["state"] == second.status()["state"] == "running"
        assert where.held(where.at())["pid"] == machine
        for one in (workspace, other):
            (one / "go").write_text("")
        assert until(
            lambda: all(
                any(said["type"] == "ended" for said in list(one))
                for one in seen.values()
            )
        )

        def said() -> list[str]:
            return sorted(
                one.read_text() for one in (home() / "epics").rglob("host.log")
            )

        assert until(lambda: len(said()) == 2)
        assert said() == [
            "first said straight to a descriptor\n",
            "second said straight to a descriptor\n",
        ]
    finally:
        for link in links:
            link.close()
        for one in (workspace, other):
            (one / "go").write_text("")
        for one in (first, second):
            if one.alive:
                one.kill()


#: A run holding a container until it is ended from outside: it says it has one, and waits.
WAITS = """
from hmz.flows import AgentCollection, Env, EnvCollection, FilesEnvMixin, FlowParams
from hmz.flows import ImageEnvMixin, ShellEnvMixin, flow


class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"


class Envs(EnvCollection):
    box: Box


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="waits")
async def waits(task, *, agents, envs, params, ctx):
    await envs["box"].write("up.txt", b"up")
    await envs["box"].exec(["sleep", "240"], timeout=300)
"""


@pytest.fixture
def slow_to_go(standin: Standin) -> Standin:
    """A `docker` slower to take a container down than a host going waits for its frontends.

    Said before the host is started, which is the process that runs it.
    """
    standin.set("STANDIN_RM_SECONDS", "8")
    return standin


@pytest.mark.timeout(90)
def test_a_host_terminated_takes_the_containers_of_its_runs_down_first(
    slow_to_go: Standin, hosted: daemon.Daemon, workspace: Path
) -> None:
    """Rather than go while its run is still letting go of what it made."""
    written(workspace, "waits", WAITS)
    work = workspace / "work"
    work.mkdir()
    with hosted.link(name="starter") as link:
        link.start(
            "waits", "go", envs={"box": f"docker@local{work}"}, budget={"cost": 1}
        )
        assert until((work / "up.txt").exists)

    assert hosted.kill()
    assert ["removed", "--force", "c0ffee"] in [
        one["argv"] for one in slow_to_go.said()
    ]


def test_a_workspace_held_by_an_older_humanize_is_not_hosted_as_well(
    older: daemon.Daemon,
) -> None:
    with pytest.raises(OSError, match="older humanize"):
        daemon.host()
    with pytest.raises(OSError, match="host"):
        older.link()


def test_a_workspace_an_older_humanize_left_a_host_in_is_not_hosted_as_well(
    left: daemon.Daemon, workspace: Path
) -> None:
    """Found where it was kept then, rather than a host of this humanize started beside it."""
    with pytest.raises(
        OSError, match=f"the runs in {where.workspace(workspace)} are held"
    ):
        daemon.host()
    assert [one.workspace for one in daemon.daemons()] == []


@pytest.mark.timeout(90)
def test_the_interface_line_opens_one_more_frontend_of_the_runs_here(
    hosted: daemon.Daemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(cli.APART, raising=False)
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)
    seen: dict[str, Any] = {}

    class Stands:
        return_code = 0

        def __init__(self, **said: Any) -> None:
            seen.update(said)

        def run(self) -> None:
            seen["status"] = hosted.status()
            seen["link"].close()

    monkeypatch.setattr("hmz.tui.Humanize", Stands)

    assert cli.opens() == 0

    assert [one["kind"] for one in seen["status"]["clients"]] == ["tui"]
    # The last frontend gone with nothing running, the host goes with it.
    assert until(lambda: not hosted.alive)
