"""Where a driver puts each session's harness, as the affinity of its runtime says to.

Nothing is reached: what the environment's machine would answer about its CLI is answered here
instead, the runtimes an affinity names are machines held in hand, and what is checked is what
the session's machine comes to for each answer.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import (
    EnvBackendKind,
    EnvConnectionError,
    HarnessKind,
    HarnessNotInstalled,
    HarnessSandboxed,
    HarnessUnrecoverable,
    HookKind,
    Permission,
    PermissionKind,
    ResourceUnmet,
)
from hmz.runtime.epic import harnessed
from hmz.runtime.flowing.affinity import Harbors
from hmz.runtime.flowing.harnesses import HarnessDriver, open_agent
from hmz.runtime.flowing.specs import AgentSpec
from hmz.runtime.flowing.spi import Placement

if TYPE_CHECKING:
    from hmz.coganchor.machines import MachineConfig
    from hmz.flows import EnvError, HarnessError
    from hmz.runtime.flowing.spi import EnvDriver

#: A container the work is in, as a docker environment places a session in it.
_WORK = Placement(
    EnvBackendKind.DOCKER,
    "work",
    PurePosixPath("/srv/repo"),
    AnchoredConfig(
        anchor=AnchorConfig(
            target="docker://work", workspace="/srv/repo", shadow="/tmp/mirror"
        )
    ),
)

#: A directory here, as the workspace places one.
_HERE = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/tmp"))

#: A role granted everything, which nothing fences.
_OPEN = Permission(
    local=PermissionKind.ALL,
    user=PermissionKind.ALL,
    system=PermissionKind.ALL,
    online=PermissionKind.ALL,
)


class _Machine:
    """A runtime an affinity names, as the environment it was opened as places one."""

    def placement(self) -> Placement:
        return Placement(
            EnvBackendKind.SSH,
            "box",
            PurePosixPath("~"),
            AnchoredConfig(anchor=AnchorConfig(target="ssh://box")),
        )


class _Harbors(Harbors):
    """A run's harness runtimes, with the work's affinity and each runtime's answer in hand."""

    def __init__(
        self,
        affinity: tuple[str, ...],
        machines: dict[str, EnvError | ResourceUnmet | None] | None = None,
    ) -> None:
        super().__init__()
        self._said = affinity
        self._machines = machines or {}
        self.opened: list[str] = []

    def affinity(self, placement: Placement) -> tuple[str, ...]:
        return self._said if placement.provider == "work" else ()

    async def machine(self, entry: str) -> EnvDriver | EnvError | ResourceUnmet:
        self.opened.append(entry)
        said = self._machines.get(entry)
        return cast("EnvDriver", _Machine()) if said is None else said


def _driver(
    monkeypatch: pytest.MonkeyPatch,
    answer: tuple[type[HarnessError], str] | None = None,
    harbors: Harbors | None = None,
) -> tuple[HarnessDriver, list[str]]:
    """A Claude Code driver of a run with these harness runtimes, and whom it asked of its CLI."""
    asked: list[str] = []

    async def has_cli(
        self: HarnessDriver, anchor: AnchorConfig, *_: Any
    ) -> tuple[type[HarnessError], str] | None:
        del self
        asked.append(anchor.target)
        return answer

    monkeypatch.setattr(HarnessDriver, "_has_cli", has_cli)
    spec = AgentSpec("coder", HarnessKind.CLAUDE, "", "m", "", "claude")
    return open_agent(spec, harbors), asked


async def _placed(
    driver: HarnessDriver,
    placement: Placement,
    *,
    hung: frozenset[HookKind] = frozenset(),
    permission: Permission = _OPEN,
) -> MachineConfig | None:
    """Where the driver puts a session working there."""
    config = driver._configured(permission, placement, hung)
    return await driver._harnessed(placement, config, hung=hung)


_MISSING = (HarnessNotInstalled, "claude is not installed on it")


# ------------------------------------------------------------------------ no affinity


async def test_with_no_affinity_the_cli_the_environment_has_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, asked = _driver(monkeypatch)
    machine = await _placed(driver, _WORK)
    assert isinstance(machine, AnchoredConfig)
    assert machine.anchor.native
    assert machine.anchor.shadow is None  # a native turn has no mirror here
    assert harnessed(machine) == "self"
    # Asked once per machine, however many sessions go there.
    await _placed(driver, _WORK)
    assert asked == ["docker://work"]


async def test_with_no_affinity_the_harness_stays_here_where_the_cli_is_not_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, _ = _driver(monkeypatch, _MISSING, _Harbors(()))
    machine = await _placed(driver, _WORK)
    assert machine == _WORK.machine
    assert harnessed(machine) == "local"


@pytest.mark.parametrize(
    "hook", [HookKind.PRE_TOOL_USE, HookKind.PERMISSION_REQUEST], ids=str
)
async def test_with_no_affinity_a_gated_session_stays_here(
    hook: HookKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A hook that decides whether a tool runs is only a watcher on another machine."""
    driver, asked = _driver(monkeypatch)
    hung = frozenset({hook, HookKind.ASK_USER})
    assert await _placed(driver, _WORK, hung=hung) == _WORK.machine
    assert asked == []


async def test_with_no_affinity_a_question_goes_to_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A question the agent asks comes back down the CLI's stream from wherever it runs."""
    driver, asked = _driver(monkeypatch)
    machine = await _placed(driver, _WORK, hung=frozenset({HookKind.ASK_USER}))
    assert harnessed(machine) == "self"
    assert asked == ["docker://work"]


@pytest.mark.parametrize("affinity", [(), ("self",), ("docker:b", "self")])
async def test_work_here_has_its_harness_here(
    affinity: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    harbors = _Harbors(affinity)
    driver, asked = _driver(monkeypatch, harbors=harbors)
    assert await _placed(driver, _HERE) is None
    assert (asked, harbors.opened) == ([], [])


# --------------------------------------------------------------------------- affinity


async def test_the_first_entry_with_room_is_taken_and_nothing_after_it_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harbors = _Harbors(("local", "self", "docker:b"))
    driver, asked = _driver(monkeypatch, harbors=harbors)
    assert await _placed(driver, _WORK) == _WORK.machine
    assert (asked, harbors.opened) == ([], [])


async def test_self_runs_the_cli_the_environment_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, asked = _driver(monkeypatch, harbors=_Harbors(("self", "local")))
    machine = await _placed(driver, _WORK)
    assert harnessed(machine) == "self"
    assert asked == ["docker://work"]


@pytest.mark.parametrize(
    "hook", [HookKind.PRE_TOOL_USE, HookKind.PERMISSION_REQUEST], ids=str
)
async def test_self_said_outright_is_not_kept_here_by_a_gate(
    hook: HookKind, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, _ = _driver(monkeypatch, harbors=_Harbors(("self",)))
    machine = await _placed(driver, _WORK, hung=frozenset({hook}))
    assert harnessed(machine) == "self"


@pytest.mark.parametrize(
    "answer",
    [_MISSING, (HarnessSandboxed, "it cannot fence the agent")],
    ids=["missing", "unfenceable"],
)
async def test_self_without_room_gives_way_to_the_next(
    answer: tuple[type[HarnessError], str], monkeypatch: pytest.MonkeyPatch
) -> None:
    driver, _ = _driver(monkeypatch, answer, _Harbors(("self", "local")))
    assert await _placed(driver, _WORK) == _WORK.machine


async def test_self_that_cannot_be_asked_is_refused_rather_than_passed_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, _ = _driver(
        monkeypatch,
        (HarnessUnrecoverable, "work did not say"),
        _Harbors(("self", "local")),
    )
    with pytest.raises(HarnessUnrecoverable, match="work did not say"):
        await _placed(driver, _WORK)


async def test_a_runtime_puts_the_harness_on_a_machine_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harbors = _Harbors(("ssh:box", "local"))
    driver, asked = _driver(monkeypatch, harbors=harbors)
    machine = await _placed(driver, _WORK)
    assert isinstance(machine, AnchoredConfig)
    assert (machine.anchor.target, machine.anchor.harness) == (
        "docker://work",
        "ssh://box",
    )
    assert machine.anchor.shadow is None  # that machine keeps a mirror of its own
    assert (asked, harbors.opened) == ([], ["ssh:box"])


@pytest.mark.parametrize(
    "refusal",
    [
        ResourceUnmet("docker@b runs 0 of the 0 containers it may"),
        EnvConnectionError("could not connect to docker@b"),
    ],
    ids=["full", "unreachable"],
)
async def test_a_runtime_without_room_gives_way_to_the_next(
    refusal: EnvError | ResourceUnmet, monkeypatch: pytest.MonkeyPatch
) -> None:
    harbors = _Harbors(("docker:b", "self", "local"), {"docker:b": refusal})
    driver, asked = _driver(monkeypatch, _MISSING, harbors)
    assert await _placed(driver, _WORK) == _WORK.machine
    assert (asked, harbors.opened) == (["docker://work"], ["docker:b"])


async def test_a_role_held_to_a_fence_cannot_have_its_harness_on_another_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fence is drawn around this machine's paths; a harness elsewhere is not in them."""
    driver, _ = _driver(monkeypatch, harbors=_Harbors(("ssh:box", "local")))
    assert await _placed(driver, _WORK, permission=Permission()) == _WORK.machine


async def test_with_no_room_anywhere_the_last_refusal_is_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harbors = _Harbors(
        ("self", "docker:b"), {"docker:b": ResourceUnmet("docker@b is full")}
    )
    driver, _ = _driver(monkeypatch, _MISSING, harbors)
    with pytest.raises(ResourceUnmet, match=r"self, docker:b.*docker@b is full"):
        await _placed(driver, _WORK)


# ------------------------------------------------------------------------ before the run


async def test_an_affinity_with_no_room_is_refused_before_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked of every machine the run has, and remembered for the sessions that go there."""
    driver, asked = _driver(monkeypatch, _MISSING, _Harbors(("self",)))
    with pytest.raises(HarnessNotInstalled, match="not installed on it"):
        await driver.placeable([_HERE, _WORK], _OPEN)
    with pytest.raises(HarnessNotInstalled):
        await _placed(driver, _WORK)
    assert asked == ["docker://work"]


async def test_the_runtimes_an_affinity_takes_are_opened_before_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harbors = _Harbors(("docker:b", "ssh:box"), {"docker:b": ResourceUnmet("full")})
    driver, _ = _driver(monkeypatch, harbors=harbors)
    await driver.placeable([_HERE, _WORK], _OPEN)
    assert harbors.opened == ["docker:b", "ssh:box"]


async def test_a_fenced_role_is_refused_before_the_run_where_only_a_runtime_is_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, _ = _driver(monkeypatch, harbors=_Harbors(("ssh:box",)))
    with pytest.raises(
        HarnessSandboxed, match="a fence cannot hold a harness that runs on another"
    ):
        await driver.placeable([_HERE, _WORK], Permission())
    await driver.placeable([_HERE, _WORK], _OPEN)


async def test_with_no_affinity_nothing_is_asked_before_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its harness goes wherever it can, so nothing refuses it up front."""
    driver, asked = _driver(monkeypatch, _MISSING, _Harbors(()))
    await driver.placeable([_HERE, _WORK], Permission())
    assert asked == []
