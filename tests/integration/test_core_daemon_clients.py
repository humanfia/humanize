"""The SDK and `hmz exec` as clients of a daemon: no epic is run in the process that asked.

An epic of specs is held by this machine's daemon -- stood in by one of the test's own,
listening on the test's socket -- on an exec slot of its own, so that `hmz exec` killed outright
leaves it going. An epic of driver objects is held by a private daemon of the calling process,
which leaves nothing behind in this machine's daemon directory and goes as the epic ends.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon import where
from hmz.flows import (
    CapabilityMissing,
    GoalCommandAgentMixin,
    HarnessKind,
    ParamsError,
    RequirementError,
)
from hmz.sdk import Client, Hmz, Refused, fakes
from tests.integration.doubles_core import install, write_flow

if TYPE_CHECKING:
    from collections.abc import Callable

#: Waits for a file `go`, then writes `done` and returns what it was asked.
WAITS = """
import asyncio
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def waits(task, *, agents, envs, params, ctx):
    while not Path("go").exists():
        await asyncio.sleep(0.02)
    Path("done").write_text(task)
    return {"asked": task}
"""

#: Fails as a flow fails.
FAILS = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def fails(task, *, agents, envs, params, ctx):
    raise ValueError(f"no {task}")
"""


#: A flow on fakes: asks its coder once and returns an object of its own, or raises.
FAKED = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, flow


class Made:
    def __init__(self, said):
        self.said = said


class Agents(AgentCollection):
    coder: Agent


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def faked(task, *, agents, envs, params, ctx):
    said = await agents["coder"].run(task, session=await agents["coder"].spawn())
    if said == "break":
        raise KeyError(said)
    return Made(said)
"""


def _until(what: Callable[[], object], seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.05)
    return bool(what())


def _exec(flow: str, task: str) -> list[str]:
    """`hmz exec` of a flow that drives no agent, as a program."""
    return [
        sys.executable,
        "-m",
        "hmz",
        "exec",
        "-f",
        flow,
        "-p",
        "budget.cost=1",
        task,
    ]


def _temporaries() -> set[str]:
    """What is in this test's temporary directory, which a private daemon makes its own in."""
    return {one.name for one in Path(tempfile.gettempdir()).iterdir()}


def _running() -> list[dict[str, Any]]:
    """What this machine's daemon says runs, host by host."""
    with Client.local() as client:
        return list(client.call("hosts.running", {})["running"])


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    at = install(tmp_path, monkeypatch)
    write_flow(at / ".hmz" / "flows", "waits", WAITS)
    write_flow(at / ".hmz" / "flows", "fails", FAILS)
    return at


@pytest.mark.usefixtures("daemon")
def test_an_epic_of_specs_is_held_on_an_exec_slot_and_returns_what_its_end_says(
    project: Path,
) -> None:
    (project / "go").touch()

    assert Hmz(project).run("waits:waits", "this", budget={"cost": 1}).run() == {
        "asked": "this"
    }
    assert (project / "done").read_text() == "this"


@pytest.mark.usefixtures("daemon")
def test_an_epic_that_fails_raises_what_its_host_said(project: Path) -> None:
    with pytest.raises(RuntimeError, match="no luck"):
        Hmz(project).run("fails:fails", "luck", budget={"cost": 1}).run()


@pytest.mark.usefixtures("daemon")
def test_an_epic_refused_before_it_starts_is_refused_with_the_daemons_code(
    project: Path,
) -> None:
    with pytest.raises(Refused, match="requires a budget") as refused:
        Hmz(project).run("waits:waits", "this")
    assert refused.value.code == 400


@pytest.mark.usefixtures("daemon")
def test_hmz_exec_killed_outright_leaves_its_epic_going_in_the_daemon(
    project: Path,
) -> None:
    going = subprocess.Popen(
        _exec("waits:waits", "killed"),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert _until(
            lambda: any(one["slot"].startswith("exec:") for one in _running())
        )
        going.send_signal(signal.SIGKILL)
        going.wait(30)
    finally:
        going.kill()

    (project / "go").touch()
    assert _until((project / "done").exists)
    assert (project / "done").read_text() == "killed"
    assert _until(lambda: _running() == [])


@pytest.mark.usefixtures("daemon")
def test_hmz_exec_follows_its_epic_to_the_end_and_says_what_failed(
    project: Path,
) -> None:
    ran = subprocess.run(
        _exec("fails:fails", "luck"),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert ran.returncode == 1, ran.stderr
    assert "ValueError: no luck" in ran.stderr


def test_hmz_exec_with_no_daemon_to_be_had_says_so(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del project
    unwritable = Path(tempfile.gettempdir()) / f"humanize-{os.getuid()}"
    unwritable.mkdir(mode=0o700, exist_ok=True)
    unwritable.chmod(0o777)
    try:
        ran = subprocess.run(
            _exec("waits:waits", "x"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        unwritable.chmod(0o700)
    del monkeypatch

    assert ran.returncode == 1
    assert ran.stderr.startswith("hmz: the daemon cannot be reached: ")


async def test_run_fake_runs_through_a_private_daemon_that_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = install(tmp_path, monkeypatch)
    write_flow(project / ".hmz" / "flows", "faked", FAKED)
    machine = where.at()
    before = _temporaries()
    coder = fakes.FakeAgentDriver(HarnessKind.CLAUDE, reply="built")

    returned = await fakes.run_fake("faked:faked", "build it", agents={"coder": coder})

    # The object itself, not its JSON: the private daemon is in this process.
    assert (type(returned).__name__, returned.said) == ("Made", "built")
    assert coder.prompts == ["build it"]
    with pytest.raises(KeyError):
        await fakes.run_fake(
            "faked:faked",
            "x",
            agents={"coder": fakes.FakeAgentDriver(HarnessKind.CLAUDE, reply="break")},
        )
    # Nothing of this machine's daemon, and nothing of the private one's, is left.
    assert not (machine / where.SOCKET).exists()
    assert _temporaries() == before
    assert Hmz(project).epics.all() == []


#: A flow whose one role asks for a mixin not every CLI serves, and whose params are typed.
AIMS = """
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowParams,
    GoalCommandAgentMixin,
    flow,
)


class Goaler(Agent, GoalCommandAgentMixin):
    pass


class Agents(AgentCollection):
    worker: Goaler


class Rounds(FlowParams):
    rounds: int = 1


@flow(agents=Agents, envs=EnvCollection, params=Rounds)
async def aims(task, *, agents, envs, params, ctx):
    return params.rounds
"""


async def test_run_fake_raises_the_flow_apis_exception_for_a_run_refused_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = install(tmp_path, monkeypatch)
    write_flow(project / ".hmz" / "flows", "aims", AIMS)
    before = _temporaries()
    lacking = next(
        kind
        for kind in HarnessKind
        if GoalCommandAgentMixin not in fakes.FakeAgentDriver(kind).capabilities
    )

    with pytest.raises(CapabilityMissing, match="needs GoalCommandAgentMixin"):
        await fakes.run_fake(
            "aims:aims", agents={"worker": fakes.FakeAgentDriver(lacking)}
        )
    with pytest.raises(ParamsError, match="rounds"):
        await fakes.run_fake("aims:aims", params={"rounds": "many"})
    with pytest.raises(RequirementError, match="no agent role 'nobody'"):
        await fakes.run_fake("aims:aims", agents={"nobody": "x"})

    assert await fakes.run_fake("aims:aims", params={"rounds": 3}) == 3
    assert _temporaries() == before
