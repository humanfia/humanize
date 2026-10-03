"""The command lines an Apple container machine hands `container`, read off a stand-in.

The stand-in is the `container` of `tests/machines/fixtures.py`: it records every argv it is
given and does just enough of what Apple's does for a machine to come up through it -- `run`
writes the id it made into the file it was told to, and `exec` runs what it was handed on this
machine, with the container's `/tmp/humanize` moved into the test's own directory -- so the
bundle is installed, the serving half starts, and the handshake a machine is observed with is
a real one. Apple's own is `tests/system/machines/`'s and `tests/system/flows/`'s.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import AppleContainerConfig, Mapped
from hmz.coganchor.machines.store import AppleContainerRuntime
from hmz.coganchor.transport import Road, Target
from hmz.sdk import Hmz
from tests.machines.fixtures import IMAGE, Standin

if TYPE_CHECKING:
    from pathlib import Path


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "here.txt").write_text("written here\n")
    return workspace


def _value(argv: list[str], flag: str) -> list[str]:
    """Every value `flag` was given in one argv."""
    return [argv[at + 1] for at, word in enumerate(argv[:-1]) if word == flag]


def test_a_container_is_started_reached_and_taken_down_through_container(
    apple_standin: Standin, tmp_path: Path
) -> None:
    workspace = _workspace(tmp_path)
    machine = AppleContainerConfig(
        image=IMAGE,
        workspace=str(workspace),
        cpus=2,
        memory=1 << 30,
        run_args=("--dns", "1.1.1.1"),
        env={"A": "b"},
        labels={"team": "x", "humanize.cpus": "64"},
    ).create()

    anchor = machine.start()
    try:
        assert anchor.target == f"apple-container://{Target.parse(anchor.target).host}"
        assert anchor.workspace == str(workspace)
        with Mapped(anchor) as held:
            assert held.read_text("here.txt") == "written here\n"
            held.write_text("there.txt", "written through the stand-in\n")
            assert held.run(["/bin/sh", "-c", "exit 0"]).ok
    finally:
        machine.stop()

    assert (workspace / "there.txt").read_text() == "written through the stand-in\n"
    asked = [one["argv"] for one in apple_standin.said()]
    (run,) = [argv for argv in asked if argv[:2] == ["run", "--detach"]]
    name = _value(run, "--name")[0]
    assert _value(run, "--progress") == ["none"]
    assert _value(run, "--user") == [f"{os.getuid()}:{os.getgid()}"]
    assert _value(run, "--workdir") == [str(workspace)]
    assert _value(run, "--mount")[0] == (
        f"type=bind,source={workspace},target={workspace}"
    )
    assert _value(run, "--env") == ["HOME=/tmp", "A=b"]
    # Humanize's labels are its own, and say what the container was given.
    assert _value(run, "--label") == [
        "team=x",
        f"humanize={os.getuid()}",
        "humanize.cpus=2",
        f"humanize.memory={1 << 30}",
    ]
    assert (_value(run, "--cpus"), _value(run, "--memory")) == (["2"], [str(1 << 30)])
    assert run.index("--dns") < run.index("--cpus") < run.index(IMAGE)
    assert any(argv[:3] == ["exec", "-i", name] for argv in asked)
    # And what is removed is what `container` said it made.
    assert asked[-1] == ["delete", "--force", name]


def test_a_container_that_would_not_start_is_removed_by_the_id_it_was_given(
    apple_standin: Standin, tmp_path: Path
) -> None:
    apple_standin.set("STANDIN_REFUSE", "1")
    machine = AppleContainerConfig(
        image=IMAGE, workspace=str(_workspace(tmp_path)), name="mine"
    ).create()

    with pytest.raises(RuntimeError, match="failed to bootstrap the container"):
        machine.start()

    assert apple_standin.said()[-1]["argv"] == ["delete", "--force", "mine"]


def test_a_name_somebody_else_holds_is_never_removed(
    apple_standin: Standin, tmp_path: Path
) -> None:
    """`container` made nothing, so there is nothing of this machine's to take down."""
    apple_standin.set("STANDIN_TAKEN", "1")
    machine = AppleContainerConfig(
        image=IMAGE, workspace=str(_workspace(tmp_path)), name="somebody-elses"
    ).create()

    with pytest.raises(RuntimeError, match="already exists"):
        machine.start()

    assert "delete" not in [one["argv"][0] for one in apple_standin.said()]


@pytest.mark.parametrize("named", ["not-there", "a,b"])
def test_a_workspace_that_cannot_be_given_is_refused_before_anything_runs(
    apple_standin: Standin, tmp_path: Path, named: str
) -> None:
    workspace = tmp_path / named
    if "," in named:
        workspace.mkdir()
    machine = AppleContainerConfig(image=IMAGE, workspace=str(workspace)).create()

    with pytest.raises((FileNotFoundError, ValueError), match=r"no directory|comma"):
        machine.start()

    assert apple_standin.said() == []


def test_what_a_stopped_container_said_is_asked_of_container(
    apple_standin: Standin,
) -> None:
    apple_standin.set("STANDIN_STOPPED", "1")
    road = Road.to(Target.parse("apple-container://box"))

    with pytest.raises(
        ConnectionError, match="the container said: humanize: no python"
    ):
        road.installed()

    assert [one["argv"][:2] for one in apple_standin.said()] == [
        ["exec", "-i"],
        ["logs", "-n"],
    ]


def test_apple_containers_checked_say_what_the_mac_has(
    apple_standin: Standin,
) -> None:
    del apple_standin

    checked = Hmz().runtimes.check(AppleContainerRuntime(name="mac", cpus=1000))

    assert checked.reached, checked.said
    assert (checked.cpus, checked.version) == (8.0, "1.5.0")
    assert checked.memory > 0
    assert checked.short == ("it is to hand out 1000 CPUs and has 8",)


def test_apple_containers_that_are_not_running_say_why(
    apple_standin: Standin,
) -> None:
    apple_standin.set("STANDIN_DOWN", "1")

    checked = Hmz().runtimes.check(AppleContainerRuntime(name="mac"))

    assert not checked.reached
    assert "apiserver is not running" in checked.said
