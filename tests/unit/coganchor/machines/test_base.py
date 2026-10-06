from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import (
    Anchored,
    AnchoredConfig,
    MachineBase,
    MachineConfig,
)
from hmz.coganchor.places import MANAGED, NATIVE_CLI, REMOTE, SUPERVISED

if TYPE_CHECKING:
    from tests.unit.coganchor.machines.conftest import Handshake


@dataclass(frozen=True, kw_only=True)
class Promised(MachineConfig):
    """A machine whose settings promise whatever they are told to."""

    promises: frozenset[str] = frozenset()

    @property
    def capabilities(self) -> frozenset[str]:
        return self.promises

    def create(self) -> Machine:
        return Machine(self)


class Machine(MachineBase):
    def start(self) -> AnchorConfig:
        return AnchorConfig(target="local:/srv/far")


def test_a_setting_comes_to_nothing_it_does_not_say() -> None:
    @dataclass(frozen=True, kw_only=True)
    class Bare(MachineConfig):
        def create(self) -> Machine:
            return Machine(self)

    assert Bare().capabilities == frozenset()
    assert Bare().create().capabilities == frozenset()


def test_a_machine_says_what_its_settings_say_before_it_is_reached() -> None:
    assert Promised(promises=frozenset({MANAGED})).create().capabilities == {MANAGED}


def test_stopping_a_machine_nobody_here_started_does_nothing() -> None:
    machine = Promised().create()

    machine.stop()


def test_what_a_reached_machine_says_of_itself_is_added(
    handshake: Handshake,
) -> None:
    machine = Promised(promises=frozenset({REMOTE})).create()
    anchor = machine.start()

    seen = machine.observe(anchor)

    assert seen == {REMOTE, "linux"}
    assert machine.capabilities == seen
    assert handshake.asked == [anchor]


def test_a_platform_nothing_has_a_name_for_adds_nothing(handshake: Handshake) -> None:
    handshake.platform = "plan9"
    machine = Promised().create()

    assert machine.observe(machine.start()) == frozenset()


def test_a_machine_that_is_not_the_platform_promised_is_refused(
    handshake: Handshake,
) -> None:
    handshake.platform = "darwin"
    machine = Promised(promises=frozenset({"linux", MANAGED})).create()

    with pytest.raises(RuntimeError, match="cannot serve linux: it says it is darwin"):
        machine.observe(machine.start())
    assert machine.capabilities == {"linux", MANAGED}


def test_a_machine_that_cannot_be_reached_says_so(handshake: Handshake) -> None:
    handshake.fails = OSError("unreachable")
    machine = Promised().create()

    with pytest.raises(OSError, match="unreachable"):
        machine.observe(machine.start())


@pytest.mark.parametrize(
    ("anchor", "road"),
    [
        (AnchorConfig(target="ssh://box"), SUPERVISED),
        (AnchorConfig(target="ssh://box", native=True), NATIVE_CLI),
    ],
)
def test_an_anchored_machine_is_remote_down_the_road_its_anchor_names(
    anchor: AnchorConfig, road: str
) -> None:
    config = AnchoredConfig(anchor=anchor)

    assert config.capabilities == {REMOTE, road}
    assert MANAGED not in config.capabilities


def test_an_anchored_machine_answers_with_its_anchor_and_takes_nothing_down() -> None:
    anchor = AnchorConfig(target="ssh://box")

    machine = AnchoredConfig(anchor=anchor).create()

    assert isinstance(machine, Anchored)
    assert machine.start() is anchor
    machine.stop()
    assert machine.start() is anchor
