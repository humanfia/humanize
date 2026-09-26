"""A container really started, and the turns that then run inside it.

Every test here brings up a container of a pulled image and takes it down again, because the
things being checked are the ones only a real one can answer: that the workspace is the
directory this machine already had rather than a copy, that a turn ran somewhere that is not
this host, and that the container is gone when whatever asked for it is done with it. A
stand-in cannot say any of that -- it would only repeat what the test told it.

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

from hmz.coganchor import check
from hmz.coganchor.agents import AgentConfig
from hmz.coganchor.machines import DockerConfig
from tests.machines.fixtures import IMAGE
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


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
