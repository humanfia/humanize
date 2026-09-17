"""A container really started, and the turns and flows that then run inside it.

Every test here brings up a container of a pulled image and takes it down again, because the
things being checked are the ones only a real one can answer: that the workspace is the
directory this machine already had rather than a copy, that a turn ran somewhere that is not
this host, that a flow naming an image lands its agent there, and that the container is gone
when the run that asked for it ends. A stand-in cannot say any of that -- it would only repeat
what the test told it.

That means a docker daemon, a pulled `python:3.12-slim`, and a user who may talk to the
socket. CI is not given those, so CI does not run this file; the half that needs none of them
is `tests/integration/machines/test_isolation.py`, which drives the same wiring -- when a
machine is started, when it is taken down -- against a machine that brings nothing up.
"""

from __future__ import annotations

import os
import socket
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import check
from hmz.coganchor.agents import AgentConfig
from hmz.coganchor.machines import DockerConfig
from hmz.runtime.runner import Runner
from tests.machines.fixtures import IMAGE
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path


def _inspect(container: str, field: str) -> str:
    """What docker says about one container, or "" when there is no such container."""
    found = subprocess.run(
        ["docker", "inspect", "--format", field, container],
        capture_output=True,
        text=True,
        check=False,
    )
    return found.stdout.strip() if found.returncode == 0 else ""


def test_the_container_holds_the_workspace_as_this_user(
    daemon: None, tmp_path: Path
) -> None:
    (tmp_path / "hello.txt").write_text("only in the workspace\n")
    machine = DockerConfig(image=IMAGE, workspace=str(tmp_path)).create()

    anchor = machine.start()
    container = anchor.target.removeprefix("docker://")
    try:
        found = check(anchor)
        assert found["workspace"] == str(tmp_path)
        assert found["entries"] == 1  # the directory itself is there, not a copy of it
        assert anchor.shadow != str(tmp_path)  # the mirror is never what it mirrors

        assert _inspect(container, "{{.Config.User}}") == f"{os.getuid()}:{os.getgid()}"
        assert _inspect(container, "{{(index .Mounts 0).Source}}") == str(tmp_path)
    finally:
        machine.stop()

    assert _inspect(container, "{{.Id}}") == ""  # and it goes when it is stopped


def test_a_turn_runs_in_the_container_and_leaves_its_work_in_the_workspace(
    daemon: None, tmp_path: Path
) -> None:
    agent = ShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            machine=DockerConfig(image=IMAGE, workspace=str(tmp_path)),
        )
    )
    # `hostname` is spawned, so it runs on the target; the redirection is the shell's own, so
    # the file is written in the mirror and pushed from there.
    answer = agent.new()("hostname > stamp.txt; cat stamp.txt")

    assert answer
    assert answer != socket.gethostname()
    assert (tmp_path / "stamp.txt").read_text().strip() == answer


#: A flow that says one of its agents works in a container of an image it names, and has that
#: agent leave a mark where a person could find it afterwards.
ISOLATING = f'''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Isolated
from hmz.flows import flow


class Agents(NamedTuple):
    """The one this drives, in a container of its own."""

    tester: Annotated[AgentBase, Isolated("{IMAGE}")]


@flow
def run(agents: Agents, task: str) -> None:
    agents.tester("hostname > stamp.txt; cat /etc/os-release > which.txt")
'''


def test_a_flow_that_isolates_an_agent_runs_it_in_the_image_it_named(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isolated mode, end to end: the flow names the image and nobody configures anything.

    The container is started for the agent, the project directory is mounted into it at the
    path it already has, and the turn runs there through coganchor -- so the work is this
    machine's file in this machine's directory, and the tools that did it were the image's.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(ISOLATING)
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    Runner(tmp_path / "flow.py", [agent]).run("go")

    # Nobody said where it works, and it works in a container of the image the flow named.
    machine = agent.config.machine
    assert isinstance(machine, DockerConfig)
    assert machine.image == IMAGE
    # The work is here, and it was done there.
    assert (tmp_path / "stamp.txt").read_text().strip() != socket.gethostname()
    assert "Debian" in (tmp_path / "which.txt").read_text()


def test_a_session_may_be_opened_at_a_directory_on_the_machine_it_lands_on(
    daemon: None, tmp_path: Path
) -> None:
    """Which directory of the target, said as the target names it: the mirror follows."""
    (tmp_path / "packages" / "one").mkdir(parents=True)
    (tmp_path / "packages" / "one" / "which.txt").write_text("the package")
    agent = ShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            machine=DockerConfig(image=IMAGE, workspace=str(tmp_path)),
        )
    )

    session = agent.new(tmp_path / "packages" / "one")

    # `pwd` is the shell's own, so it says where the agent was put: the mirror of that
    # directory. What it reads and writes there is that directory's, on the target.
    assert session("cat which.txt") == "the package"
    assert session("pwd > where.txt; cat where.txt").endswith("packages/one")
    assert (tmp_path / "packages" / "one" / "where.txt").exists()


#: A flow with two agents and nothing said about where either works, which is what a run put
#: in a container from outside is: the flow did not ask for one, and every agent lands there.
CONTAINED = """
from typing import NamedTuple

from hmz.flows import Agent, container, flow


class Agents(NamedTuple):
    builder: Agent
    reviewer: Agent


@flow
def run(agents: Agents, task: str) -> None:
    agents.builder("hostname > builder.txt")
    agents.reviewer("hostname > reviewer.txt")
    held = container()
    held.write_text("from-the-flow.txt", held.run(["hostname"]).output)
"""


def test_a_run_may_be_put_in_one_container_and_every_agent_lands_there(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the convenience: said once from outside rather than agent by agent inside.

    One container for the run rather than one apiece, so that what one agent writes is what
    the next one reads -- and the flow's own code reaches the same place, which is the half a
    mounted workspace does not answer for.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(CONTAINED)
    agents = [
        ShellAgent(AgentConfig(model="m", effort="high")),
        ShellAgent(AgentConfig(model="m", effort="high")),
    ]

    Runner(tmp_path / "flow.py", agents, container=IMAGE).run("go")

    # Both turns ran on the machine, and on the same one.
    said = [
        (tmp_path / one).read_text().strip()
        for one in ("builder.txt", "reviewer.txt", "from-the-flow.txt")
    ]
    assert said[0] == said[1] == said[2]
    assert said[0] != socket.gethostname()
    # And it is taken down when the run ends, whichever way it ends.
    assert _inspect(said[0], "{{.State.Running}}") == ""


#: The flow a contained run is started at, which calls one whose place says nothing about
#: where its agent works -- which is what every flow written before this said.
CALLING = '''"""Calls a flow that says nothing about where its agent works."""

from hmz.flows import Agent, flow, load


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    agent.new()("hostname > calling.txt")
    load("called")(agents, task)
'''

#: And the one it calls, which has its agent leave a mark saying where the turn ran.
CALLED = '''"""The one that is called, driving the agents it was handed."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    agent.new()("hostname > called.txt")
'''


def test_a_run_in_a_container_may_call_a_flow_that_says_where_nobody_works(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A place that says nothing refuses a machine somebody chose, and this is not one.

    The run's container was said once from outside, about every agent, by whoever started
    the run -- so a called flow reading it as a machine anybody reached for would refuse
    every flow written before there was such a thing, and name itself in the refusal.
    """
    monkeypatch.chdir(tmp_path)
    written(tmp_path / ".humanize/flows", "calling", CALLING)
    written(tmp_path / ".humanize/flows", "called", CALLED)
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    Runner("calling", [agent], container=IMAGE).run("go")

    # The call went through, and its turn ran in the run's container rather than here --
    # the same one the flow that called it was working in, which is the point of one
    # container for the run: what the caller wrote is what the called flow reads.
    called = (tmp_path / "called.txt").read_text().strip()
    assert called != socket.gethostname()
    assert called == (tmp_path / "calling.txt").read_text().strip()


def test_a_second_run_in_a_container_is_refused_rather_than_handed_the_first(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container is the process's rather than the run's, so there is one to be in.

    Two started at once would be two runs sharing a workspace neither was told about, and
    the second of them reading the first's container back as its own.
    """
    from hmz.flows.driving import contained

    monkeypatch.chdir(tmp_path)
    with contained(IMAGE) as where_:
        assert where_ is not None
        with (
            pytest.raises(RuntimeError, match="in a container already"),
            contained(IMAGE),
        ):
            raise AssertionError  # never reached: the refusal is at the block's opening
        # And a run on this machine is not a second run in a container: it starts nothing,
        # so there is nothing for it to be reaching for.
        with contained("") as none:
            assert none is None


def test_the_flow_reads_writes_and_runs_on_the_machine_the_run_lands_on(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half a mounted workspace does not answer for: the tools are the machine's.

    A file is the same file either way -- the project directory is mounted at the path it
    already has -- and a command is not, being run by this machine's shell against this
    machine's tools unless it is sent there.
    """
    from hmz.coganchor.machines import Mapped

    monkeypatch.chdir(tmp_path)
    (tmp_path / "here.txt").write_text("written here\n")
    machine = DockerConfig(image=IMAGE, workspace=str(tmp_path)).create()
    anchor = machine.start()
    try:
        with Mapped(anchor) as held:
            assert held.workspace == str(tmp_path)
            assert held.read_text("here.txt") == "written here\n"
            held.write_text("there.txt", "written from the flow\n")
            assert "here.txt" in held.listdir()
            assert held.exists("here.txt")
            assert not held.exists("nothing.txt")

            said = held.run(
                ["python3", "-c", "import platform; print(platform.node())"]
            )
            assert said.ok
            assert said.status == 0
            assert said.output.strip() != socket.gethostname()
            # And a command that failed says so rather than reading as one that worked.
            assert not held.run(["python3", "-c", "raise SystemExit(3)"]).ok
    finally:
        machine.stop()

    # The work is here, because the directory the container was given is this one.
    assert (tmp_path / "there.txt").read_text() == "written from the flow\n"
