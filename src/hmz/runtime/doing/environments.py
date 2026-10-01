"""The machines a flow's environments may be put on, and what each of them has.

An environment provider is an ssh host or a docker daemon written down under a name, which an
`-e` then names instead of spelling out how it is reached. The store is
:mod:`hmz.coganchor.machines.store` and reading an ssh config is
:mod:`hmz.coganchor.machines.sshconfig`; both are reached from here, and so is asking one of
them what it has -- which is the ssh probe a run itself makes, or the docker daemon's own
`docker info` -- so that a provider written down one way is one every way in offers a moment
later, and checked the same way wherever it is checked from.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from hmz.coganchor.machines.sshconfig import SSHHost
    from hmz.coganchor.machines.store import DockerProvider, EnvProvider, SSHProvider

__all__ = ["Checked", "Environments"]

#: How long a provider is given to answer when it is checked.
CHECKING = 30.0


@dataclass(frozen=True, slots=True)
class Checked:
    """What a provider said when it was asked what it has.

    Attributes:
      reached: Whether it answered at all.
      said: Why it did not, in its own words, or "" where it did.
      home: Where the login's home is, for an ssh host.
      cpus: How many CPUs it has.
      memory: How many bytes of memory.
      gpus: Its GPUs, by device id: every one it lists, answering or not.
      usable: Those of `gpus` that answer, for a docker daemon whose host could be asked
        which do; None where nobody could ask.
      gpu_memory: The bytes the smallest of those GPUs has, or 0 where nothing said.
      runtimes: The container runtimes a docker daemon offers, its default first.
      version: The docker daemon's version.
      short: What the provider was written down as handing out and it has not got.
    """

    reached: bool
    said: str = ""
    home: str = ""
    cpus: float = 0.0
    memory: int = 0
    gpus: tuple[str, ...] = ()
    usable: tuple[str, ...] | None = None
    gpu_memory: int = 0
    runtimes: tuple[str, ...] = ()
    version: str = ""
    short: tuple[str, ...] = ()


class Environments:
    """Every environment provider there is, how to make one, and asking one what it has."""

    def all(self, backend: str = "") -> list[EnvProvider]:
        """Every provider, or one backend's: by backend, then by name."""
        from hmz.coganchor.machines import store

        return store.providers(backend)

    def find(self, backend: str, name: str) -> EnvProvider | None:
        """The provider of that backend under that name, or None."""
        from hmz.coganchor.machines import store

        return store.find(backend, name)

    def where(self, backend: str, name: str) -> Path:
        """Where one is kept, whether or not it has been made.

        Raises:
          ValueError: If the backend is not `ssh` or `docker`, or the name is not one a
            provider may have -- which is what asks it of a name before it is made.
        """
        from hmz.coganchor.machines import store

        return store.where(backend, name)

    def new(self, backend: str, name: str, **fields: Any) -> EnvProvider:
        """One provider, checked, and written nowhere.

        Args:
          backend: `ssh` or `docker`.
          name: What it is to be called.
          **fields: The rest of it, by field, as `held()` writes them.

        Returns:
          It, for :meth:`add` or :meth:`write`.

        Raises:
          ValueError: For a field that backend has not got, or a value it cannot take.
        """
        from hmz.coganchor.machines import store

        return store.new(backend, name, **fields)

    def add(self, provider: EnvProvider) -> EnvProvider:
        """Writes a new provider down.

        Raises:
          ValueError: If there is one of that backend under that name already.
          OSError: If it cannot be written.
        """
        from hmz.coganchor.machines import store

        return store.add(provider)

    def write(self, provider: EnvProvider) -> EnvProvider:
        """Writes a provider down, whole, over whatever was under its name.

        Raises:
          OSError: If it cannot be written.
        """
        from hmz.coganchor.machines import store

        return store.write(provider)

    def remove(self, backend: str, name: str) -> bool:
        """Takes one away, and says whether there was one.

        Raises:
          ValueError: If the backend or the name is not one there could be.
        """
        from hmz.coganchor.machines import store

        return store.remove(backend, name)

    def hosts(self, config: str | os.PathLike[str] | None = None) -> list[SSHHost]:
        """Every host an ssh config names, each as `ssh -G` resolves it: what may be imported.

        Args:
          config: The config file, or None for the user's own.

        Raises:
          OSError: If there is no `ssh`, or it cannot read the config.
        """
        from hmz.coganchor.machines import sshconfig

        return sshconfig.hosts(config)

    def import_ssh(
        self,
        config: str | os.PathLike[str] | None = None,
        names: Iterable[str] | None = None,
        *,
        update: bool = False,
    ) -> list[SSHProvider]:
        """Writes an ssh provider down for each host an ssh config names.

        Args:
          config: The config file, or None for the user's own.
          names: The hosts to import, by their `Host`, or None for all of them.
          update: Whether to write over one of that name already there.

        Returns:
          What was written, in the order the config names them.

        Raises:
          ValueError: If `names` names a host the config does not.
          OSError: If one cannot be written.
        """
        from hmz.coganchor.machines import store

        return store.imports(config, names, update=update)

    def resolve(self, provider: SSHProvider) -> SSHHost:
        """What `ssh` makes of an ssh provider -- machine, login, port, keys -- reaching nothing.

        Raises:
          OSError: If there is no `ssh`, or it cannot read the config it is told to.
        """
        from hmz.coganchor.machines import sshconfig
        from hmz.coganchor.transport import ssh_flags

        port = ("-p", str(provider.port)) if provider.port else ()
        return sshconfig.resolve(
            provider.login(),
            (*ssh_flags(provider.settings()), *port),
            alias=provider.name,
        )

    def check(self, provider: EnvProvider, seconds: float = CHECKING) -> Checked:
        """Asks a provider what it has, waiting at most so long for it to answer.

        An ssh host is asked what a run asks one when it is first reached -- its home, CPUs,
        memory and GPUs -- down the road a run takes to it, with nobody to type a password;
        a docker daemon is asked `docker info`, and what it was written down as handing out
        is held up against what it has.

        Args:
          provider: The provider.
          seconds: How long it is given.

        Returns:
          What it said, or why it said nothing -- never raising, even for a provider that
          can no longer be reached the way it was written down.
        """
        from hmz.coganchor.machines.store import SSHProvider

        try:
            if isinstance(provider, SSHProvider):
                return _ssh(provider, seconds)
            return _docker(provider, seconds)
        except (ValueError, OSError, RuntimeError) as error:
            return Checked(reached=False, said=str(error))


def _asked(argv: list[str], seconds: float) -> tuple[int, str, str]:
    """Runs one short command with nobody to answer it, for its status and both streams.

    In a session of its own, so that an `ssh` wanting a password or a host key confirmed has
    no terminal to ask on, and told never to ask a program instead, so that it fails rather
    than waits on nobody.
    """
    try:
        said = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=seconds,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "SSH_ASKPASS_REQUIRE": "never"},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"it did not answer within {seconds:g}s"
    except OSError as error:
        return 127, "", str(error)
    return said.returncode, said.stdout, said.stderr


def _last(said: str, status: int) -> str:
    """The last thing a command said, or its status where it said nothing."""
    lines = [line for line in said.strip().splitlines() if line.strip()]
    return lines[-1].strip() if lines else f"exit status {status}"


def _ssh(provider: SSHProvider, seconds: float) -> Checked:
    """An ssh host, asked what a run asks it on the way in."""
    from hmz.coganchor.transport import Road, Target
    from hmz.flows import EnvConnectionError
    from hmz.runtime.flowing.environing_ssh import PROBE_SCRIPT, facts_of

    road = Road.to(Target.parse(provider.target()))
    status, out, err = _asked(road.line(["/bin/sh", "-c", PROBE_SCRIPT]), seconds)
    if status:
        return Checked(reached=False, said=_last(err, status))
    try:
        facts = facts_of(out)
    except EnvConnectionError as error:
        return Checked(reached=False, said=str(error))
    held = facts.resources
    return Checked(
        reached=True,
        home=str(facts.home),
        cpus=float(held.cpu_count),
        memory=held.memory,
        gpus=tuple(str(one) for one in range(held.gpu_count)),
        gpu_memory=held.gpu_memory,
    )


def _docker(provider: DockerProvider, seconds: float) -> Checked:
    """A docker daemon, asked `docker info`, and held up against what it was given.

    And, where it lists a GPU, which of them answer: a GPU that has failed since the daemon's
    CDI specs were written is listed still, and is handed to nobody -- asked of containers of
    the provider's image, as a run asks before it hands one out.
    """
    from hmz.coganchor.machines import gpus_listed, gpus_usable
    from hmz.runtime.flowing.environing_docker import IMAGE

    began = time.monotonic()
    asking = provider.daemon().docker("info", "--format", "{{json .}}")
    status, out, err = _asked(asking, seconds)
    try:
        said: object = json.loads(out) if out.strip() else {}
    except ValueError:
        said = {}
    info = cast("dict[str, Any]", said) if isinstance(said, dict) else {}
    errors = [str(one) for one in cast("list[Any]", info.get("ServerErrors") or [])]
    if status or errors or not info.get("ServerVersion"):
        return Checked(reached=False, said="; ".join(errors) or _last(err, status))
    runtimes = [str(one) for one in cast("dict[str, Any]", info.get("Runtimes") or {})]
    default = str(info.get("DefaultRuntime") or "")
    if default in runtimes:
        runtimes.remove(default)
        runtimes.insert(0, default)
    devices = cast("list[Any]", info.get("DiscoveredDevices") or [])
    gpus = gpus_listed(devices)
    # Asked afresh, in what is left of the time it was given: somebody checking may have
    # just seen to a GPU a run was told had failed.
    left = seconds - (time.monotonic() - began)
    answered = (
        gpus_usable(
            str(provider.daemon()),
            provider.image or IMAGE,
            devices,
            seconds=left,
            fresh=True,
        )
        if gpus and left > 0
        else None
    )
    usable = None if answered is None else _answering(gpus, answered)
    cpus, memory = float(info.get("NCPU") or 0), int(info.get("MemTotal") or 0)
    short: list[str] = []
    if provider.cpus > cpus:
        short.append(f"it is to hand out {provider.cpus:g} CPUs and has {cpus:g}")
    if provider.memory > memory:
        short.append(f"it is to hand out {provider.memory} bytes and has {memory}")
    if gpus and (missing := [one for one in provider.gpus if one not in gpus]):
        short.append(f"it has no GPU {', '.join(missing)}")
    if usable is not None and (
        failed := [one for one in provider.gpus if one in gpus and one not in usable]
    ):
        short.append(
            f"GPU {', '.join(failed)} "
            + ("does not answer" if len(failed) == 1 else "do not answer")
        )
    if provider.runtime and provider.runtime not in runtimes:
        short.append(f"it has no runtime {provider.runtime}")
    return Checked(
        reached=True,
        cpus=cpus,
        memory=memory,
        gpus=gpus,
        usable=usable,
        runtimes=tuple(runtimes),
        version=str(info.get("ServerVersion") or ""),
        short=tuple(short),
    )


def _answering(
    gpus: tuple[str, ...], answered: tuple[tuple[str, str], ...]
) -> tuple[str, ...]:
    """Which of the GPUs a daemon lists answer, by the ids it lists them by.

    Args:
      gpus: What it lists, by CDI name or UUID.
      answered: What answers, as `(name, uuid)`.
    """
    known = {id_ for pair in answered for id_ in pair}
    return tuple(one for one in gpus if one in known)
