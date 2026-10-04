"""An Apple container machine against Apple's own `container`, and the runtime checked there.

The machine comes up as a Linux virtual machine of its own holding the workspace this user
owns, is reached down the road a turn takes, and goes with `stop`; the runtime of them, asked
what it has, says what `container system status` and this Mac do. Skipped where `container`
is not running here or has not got the image.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import AppleContainerConfig, Mapped
from hmz.coganchor.machines.store import AppleContainerRuntime
from hmz.coganchor.transport import Target
from hmz.sdk import Hmz
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from pathlib import Path


def _there(name: str) -> bool:
    said = subprocess.run(
        ["container", "list", "--all", "--quiet"],
        capture_output=True,
        text=True,
        check=True,
    )
    return name in said.stdout.split()


@pytest.mark.timeout(300)
def test_a_container_holds_the_workspace_as_this_user_and_goes_with_stop(
    apple: None, tmp_path: Path
) -> None:
    del apple
    (tmp_path / "here.txt").write_text("written here\n")
    machine = AppleContainerConfig(image=IMAGE, workspace=str(tmp_path)).create()

    anchor = machine.start()
    name = Target.parse(anchor.target).host
    try:
        assert "linux" in machine.capabilities
        assert _there(name)
        with Mapped(anchor) as held:
            assert held.read_text("here.txt") == "written here\n"
            held.write_text("there.txt", "written in the container\n")
            ran = held.run(["/bin/sh", "-c", "uname -s; id -u"])
    finally:
        machine.stop()

    assert ran.ok, ran
    assert ran.output.split() == ["Linux", str(os.getuid())]
    assert (tmp_path / "there.txt").read_text() == "written in the container\n"
    assert (tmp_path / "there.txt").stat().st_uid == os.getuid()
    assert not _there(name)


def test_apple_containers_checked_say_what_this_mac_has(apple: None) -> None:
    del apple

    checked = Hmz().runtimes.check(AppleContainerRuntime(name="mac"))

    assert checked.reached, checked.said
    assert checked.cpus == float(os.cpu_count() or 0)
    assert checked.memory > 0
    assert checked.version
    assert checked.short == ()
