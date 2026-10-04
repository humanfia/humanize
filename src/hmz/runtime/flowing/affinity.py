"""Where an agent's harness runs: the affinity of the runtime its work is on.

A runtime may say where the harness of an agent working on it is put, as an ordered list kept
with it (:attr:`hmz.coganchor.machines.store.SSHRuntime.affinity`): another runtime, opened as
a machine of its own for the harness alone; `self`, natively on the runtime's own machine; or
`local`, here, anchored to it. The first that has room is where it goes, and the next is
looked at only where the one before has none -- a runtime that cannot be reached or has no
share left to give, a machine without the CLI or that cannot hold the fence. `local` always
has room. A runtime with no affinity, and work on anything that is not a runtime somebody
saved, is put where its CLI is -- natively where the machine has it and nothing stops it, and
here otherwise.

The affinity is the one of the runtime the work is actually on, read off where a session is
placed, so that a run moved off the runtime its line named onto another has the harnesses the
other one asks for. And it is the only one walked: a runtime a harness is put on is put on as
it is, its own affinity -- and whatever it would fall back to -- being for work on it, which a
harness is not.

:class:`Harbors` is a run's: every runtime its harnesses went to, each opened once, probed
before the flow is called, and closed with the run. The driver walks the list
(:class:`~hmz.runtime.flowing.harnesses.HarnessDriver`); this only says what is on it, and
opens what it names.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from hmz.flows import EnvBackendKind, EnvError, EnvUnavailable, ResourceUnmet

if TYPE_CHECKING:
    from hmz.coganchor.machines.store import Runtime

    from .spi import EnvDriver, Placement

__all__ = ["Harbors", "affinity_of"]


def affinity_of(runtime: Runtime | None) -> tuple[str, ...]:
    """The affinity a session on a runtime is put by: its own, or none for no runtime.

    Args:
      runtime: The runtime the work is on, as it is saved -- the one actually opened, which
        for a run moved off the runtime its line named is the one it was moved to -- or None
        for work on anything nobody saved.
    """
    return runtime.affinity if runtime is not None else ()


class Harbors:
    """The runtimes one run's harnesses may be put on, each opened the first time it is named.

    Shared by every agent of the run, so that two roles whose affinity names one runtime are
    two harnesses on one machine rather than two machines; and a runtime found to have no
    room is not asked again, by anybody.
    """

    def __init__(self) -> None:
        """Holds nothing, and has opened nothing."""
        self._affinities: dict[tuple[str, str], tuple[str, ...]] = {}
        self._opened: dict[str, EnvDriver] = {}
        self._refused: dict[str, EnvError | ResourceUnmet] = {}
        self._opening = asyncio.Lock()

    def affinity(self, placement: Placement) -> tuple[str, ...]:
        """Where a session working there has its harness put, in the order tried.

        Read off the runtime saved under the backend and the name its placement says,
        once per run.

        Args:
          placement: Where the session works.

        Returns:
          The runtime's affinity, or none for work on no runtime somebody saved.
        """
        from hmz.coganchor.machines import store

        key = (str(placement.backend), placement.provider)
        if key not in self._affinities:
            self._affinities[key] = affinity_of(store.find(*key))
        return self._affinities[key]

    async def machine(self, entry: str) -> EnvDriver | EnvError | ResourceUnmet:
        """The runtime an affinity names, opened and probed, or why it has no room.

        Opened the way an environment is, with no role -- a harness asks for nothing but
        somewhere to be -- and in the runtime's own workdir; one without, in the login's home
        over ssh, and on a daemon here in a directory humanize keeps for it.

        Args:
          entry: `<backend>:<name>`, as :func:`hmz.coganchor.machines.store.affine` reads.

        Returns:
          The machine, or the refusal that says it has no room: that it cannot be reached
          or opened, or has no share left to hand out.
        """
        from hmz.coganchor.machines import AnchoredConfig
        from hmz.runtime.epic import harbor

        from .environments import probe

        async with self._opening:
            if entry in self._opened:
                return self._opened[entry]
            if entry in self._refused:
                return self._refused[entry]
            try:
                driver = _opened(entry)
            except EnvError as why:
                self._refused[entry] = why
                return why
            try:
                await probe(driver)
            except (EnvError, ResourceUnmet) as why:
                with contextlib.suppress(Exception):
                    await driver.close()
                self._refused[entry] = why
                return why
            except BaseException:
                with contextlib.suppress(Exception):
                    await asyncio.shield(driver.close())
                raise
            self._opened[entry] = driver
            machine = driver.placement().machine
            if isinstance(machine, AnchoredConfig):
                harbor(machine.anchor.target, entry)
            return driver

    async def close(self) -> None:
        """Closes every runtime opened for a harness. Idempotent."""
        opened, self._opened = list(self._opened.values()), {}
        for driver in opened:
            with contextlib.suppress(Exception):
                await driver.close()


def _opened(entry: str) -> EnvDriver:
    """The driver of the runtime an affinity names, made and not yet reached.

    Raises:
      EnvUnavailable: If no runtime is saved under that name, or one is with no workdir and
        nowhere humanize could keep one.
    """
    from hmz import home
    from hmz.coganchor.machines import store

    from .environments import open_env
    from .specs import EnvSpec

    named = store.affine(entry)
    if named is None:
        raise EnvUnavailable(f"{entry} is not a runtime")
    backend, name = named
    found = store.find(backend, name)
    if found is None:
        raise EnvUnavailable(f"no {backend} runtime is saved as {name!r}")
    workdir = found.workdir
    if not workdir and backend == store.SSH:
        workdir = "~"
    elif not workdir and isinstance(
        found, store.DockerRuntime | store.AppleContainerRuntime
    ):
        # An Apple container is this Mac's, and so here; a docker daemon may be anywhere.
        here = True
        if isinstance(found, store.DockerRuntime):
            try:
                here = found.daemon().here
            except ValueError:
                here = False
        if not here:
            raise EnvUnavailable(
                f"{entry} has no workdir of its own to put a harness in, and its daemon "
                "is not on this machine"
            )
        kept = home() / "harness"
        kept.mkdir(parents=True, exist_ok=True)
        workdir = str(kept)
    elif not workdir:
        raise EnvUnavailable(f"{entry} has no workdir of its own to put a harness in")
    spec = EnvSpec("harness", EnvBackendKind(backend), name, PurePosixPath(workdir))
    # Traced, because the harness supervises its agent there.
    return open_env(spec, traced=True)
