"""Where a driver puts each session's harness, as `-H` says to: settled as a session opens.

Nothing is reached: what the environment's machine would answer about its CLI is answered here
instead, and what is checked is what the session's machine comes to for each answer.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import EnvBackendKind, HarnessKind, HarnessNotInstalled
from hmz.runtime.epic import harnessed
from hmz.runtime.flowing.harnesses import HarnessDriver, open_agent
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import Placement

if TYPE_CHECKING:
    from hmz.coganchor.machines import MachineConfig
    from hmz.flows import HarnessError
    from hmz.runtime.flowing.spi import EnvDriver

#: A container the work is in, as a docker environment places a session in it.
_WORK = Placement(
    EnvBackendKind.DOCKER,
    "local",
    PurePosixPath("/srv/repo"),
    AnchoredConfig(
        anchor=AnchorConfig(
            target="docker://work", workspace="/srv/repo", shadow="/tmp/mirror"
        )
    ),
)

#: A directory here, as the workspace places one.
_HERE = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/tmp"))


class _Machine:
    """A standalone harness's machine, as the environment it was opened as places one."""

    def placement(self) -> Placement:
        return Placement(
            EnvBackendKind.SSH,
            "box",
            PurePosixPath("~"),
            AnchoredConfig(anchor=AnchorConfig(target="ssh://box")),
        )


def _driver(
    mode: str,
    monkeypatch: pytest.MonkeyPatch,
    answer: tuple[type[HarnessError], str] | None = None,
    on: object = None,
) -> tuple[HarnessDriver, list[str]]:
    """A Claude Code driver told `-H mode`, and the machines it asked about its CLI."""
    asked: list[str] = []

    async def has_cli(
        self: HarnessDriver, anchor: AnchorConfig, *_: Any
    ) -> tuple[type[HarnessError], str] | None:
        del self
        asked.append(anchor.target)
        return answer

    monkeypatch.setattr(HarnessDriver, "_has_cli", has_cli)
    spec = AgentSpec("coder", HarnessKind.CLAUDE, "", "m", "", "claude")
    return open_agent(spec, mode, cast("EnvDriver | None", on)), asked


async def _placed(
    driver: HarnessDriver, placement: Placement, *, gated: bool = False
) -> MachineConfig | None:
    """Where the driver puts a session working there."""
    return await driver._harnessed(placement, driver._config, "/tmp", gated=gated)


async def test_adaptive_runs_the_cli_the_environment_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, asked = _driver("adaptive", monkeypatch)
    machine = await _placed(driver, _WORK)
    assert isinstance(machine, AnchoredConfig)
    assert machine.anchor.native
    assert machine.anchor.shadow is None  # a native turn has no mirror here
    assert harnessed(machine) == "env"
    # Asked once per machine, however many sessions go there.
    await _placed(driver, _WORK)
    assert asked == ["docker://work"]


async def test_adaptive_keeps_the_harness_here_where_the_environment_has_no_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, _ = _driver(
        "adaptive", monkeypatch, (HarnessNotInstalled, "claude is not installed")
    )
    machine = await _placed(driver, _WORK)
    assert machine == _WORK.machine
    assert harnessed(machine) == "local"


async def test_adaptive_keeps_a_gated_session_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hook that decides what the CLI may do is only a watcher on another machine."""
    driver, asked = _driver("adaptive", monkeypatch)
    assert await _placed(driver, _WORK, gated=True) == _WORK.machine
    assert asked == []


async def test_env_refuses_an_environment_without_the_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, _ = _driver(
        "env", monkeypatch, (HarnessNotInstalled, "claude is not installed on it")
    )
    with pytest.raises(HarnessNotInstalled, match="not installed on it"):
        await _placed(driver, _WORK)


async def test_local_asks_nothing_and_keeps_the_harness_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, asked = _driver("local", monkeypatch)
    assert await _placed(driver, _WORK) == _WORK.machine
    assert asked == []


@pytest.mark.parametrize("mode", ["adaptive", "env", "local"])
async def test_work_here_has_its_harness_here(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, asked = _driver(mode, monkeypatch)
    assert await _placed(driver, _HERE) is None
    assert asked == []


async def test_standalone_puts_the_harness_on_its_own_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, asked = _driver("standalone", monkeypatch, on=_Machine())
    machine = await _placed(driver, _WORK)
    assert isinstance(machine, AnchoredConfig)
    assert (machine.anchor.target, machine.anchor.harness) == (
        "docker://work",
        "ssh://box",
    )
    assert machine.anchor.shadow is None  # that machine keeps a mirror of its own
    assert harnessed(machine) == "standalone:ssh://box"
    assert asked == []

    # And work here is served to it from here.
    here = await _placed(driver, _HERE)
    assert isinstance(here, AnchoredConfig)
    assert (here.anchor.target, here.anchor.harness) == ("local", "ssh://box")
