"""When a machine is brought up and when it is taken down, checked without bringing one up.

The wiring -- one machine for an agent however many sessions it opens, gone with the agent
that started it, and never started at all for a place that was already running -- is a
question about who calls `start` and `stop` and when, so it is asked of a machine that does
neither: `_StubMachine` below records that it was asked and returns an anchor of this repo's
own. Integration rather than unit because that is what the tier is -- the agent, the runner and
the machine are driven together, and everything on the far side of them is a stand-in written
here rather than something that had to be installed.

The other half is `tests/system/machines/test_isolation.py`, which drives the same wiring
against real containers: that one needs a docker daemon and a pulled image, so CI does not run
it. What stays here is everything that can be answered without one -- including the refusal of
a workspace that is not there, which `Docker.start` makes before it has reached for `docker`
at all, and which is the whole point of its making it there: docker would have created the
directory for you, owned by root, inside a tree this user owns.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig
from hmz.coganchor.machines import (
    AnchoredConfig,
    DockerConfig,
    MachineBase,
    MachineConfig,
)
from tests.machines.fixtures import IMAGE
from tests.stubs import HereAnchor, ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor import AnchorConfig


class _StubMachine(MachineBase):
    """A machine that is only ever said to be started, and records that it was."""

    def __init__(self, config: _StubMachineConfig) -> None:
        super().__init__(config)
        self.anchor = HereAnchor(target="tcp://stub:0")
        self.started = 0
        self.stopped = 0

    def start(self) -> AnchorConfig:
        self.started += 1
        return self.anchor

    def stop(self) -> None:
        self.stopped += 1


@dataclass(frozen=True, kw_only=True)
class _StubMachineConfig(MachineConfig):
    #: Every machine this config builds, so a test can ask what became of them.
    built: list[_StubMachine]

    def create(self) -> _StubMachine:
        machine = _StubMachine(self)
        self.built.append(machine)
        return machine


def test_a_machine_is_started_for_the_first_turn_and_shared_by_the_rest() -> None:
    setting = _StubMachineConfig(built=[])
    agent = ShellAgent(AgentConfig(model="m", effort="high", machine=setting))
    assert setting.built == []  # configuring an agent starts nothing

    agent.new()("echo one")
    agent.new()("echo two")  # a second session, and still one machine
    assert len(setting.built) == 1
    assert setting.built[0].started == 1
    assert agent.anchor is setting.built[0].anchor
    # Both turns ran under it, which is what a machine of the agent's own is for.
    assert setting.built[0].anchor.seen == [
        ["sh", "-c", "echo one"],
        ["sh", "-c", "echo two"],
    ]


def test_a_machine_is_taken_down_with_the_agent_that_started_it() -> None:
    setting = _StubMachineConfig(built=[])
    agent = ShellAgent(AgentConfig(model="m", effort="high", machine=setting))
    agent.new()("echo one")
    assert setting.built[0].stopped == 0  # while the agent may still run a turn

    del agent
    gc.collect()
    assert setting.built[0].stopped == 1


def test_a_machine_that_was_already_running_is_reached_and_left_running() -> None:
    """Which is the whole of what an anchor says, and the reason it is a machine like any."""
    anchor = HereAnchor(target="ssh://build-box")
    machine = AnchoredConfig(anchor=anchor).create()

    assert machine.start() is anchor
    machine.stop()  # and there is nothing to take down


def test_a_workspace_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """Rather than mounted into being: docker would create it, owned by root, in this tree."""
    missing = tmp_path / "not-here"
    with pytest.raises(FileNotFoundError):
        DockerConfig(image=IMAGE, workspace=str(missing)).create().start()
    assert not missing.exists()
