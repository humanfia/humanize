"""The runtimes: the machines a flow's environments may be put on, written down under names.

A runtime is one machine something can be put on, named by what somebody called it rather than
by how it is reached: an ssh host with the login, port, key and jump host it takes, a docker
daemon with the resources it may hand out, a docker swarm whose manager schedules a task for
each environment onto whichever of its nodes has room, or this Mac's Apple containers with the
share of it they may have. A flow's environment is put on one
when an `-e` names it, and moved down the runtimes it falls back to where it cannot be held
there. One directory per runtime, under
`~/.humanize/runtimes/<backend>/<name>/`, holding `runtime.json`.

They were once kept under `~/.humanize/env-providers/`, each in a `provider.json`; the first
look for them moves that directory where they are kept now, and one still in a `provider.json`
is read from it until it is next written.

Nothing here reaches a machine. What one is when it is asked is
:mod:`hmz.runtime.doing.runtimes`'s, and reading the user's ssh config is
:mod:`hmz.coganchor.machines.sshconfig`'s; this is only the answer to "which ones are there, and
what is in each".
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz import home
from hmz.coganchor import atomic

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from hmz.coganchor.transport import Endpoint

__all__ = [
    "APPLE_CONTAINER",
    "BACKENDS",
    "DOCKER",
    "HERE",
    "IMPORTED",
    "SELF",
    "SPELLING",
    "SSH",
    "SWARM",
    "TYPED",
    "AppleContainerRuntime",
    "DockerRuntime",
    "Runtime",
    "SSHRuntime",
    "SwarmRuntime",
    "add",
    "affine",
    "daemon_of",
    "fallbacks",
    "find",
    "imports",
    "new",
    "node_of",
    "remove",
    "respelled",
    "runtimes",
    "under",
    "where",
    "write",
]

#: The backends a runtime may be for, by the name `-e` gives each.
SSH = "ssh"
DOCKER = "docker"
SWARM = "swarm"
APPLE_CONTAINER = "apple-container"
BACKENDS = (SSH, DOCKER, SWARM, APPLE_CONTAINER)

#: The two places a harness may be put that are not a runtime of their own, as an affinity
#: names them: natively on the machine of the runtime the work is on, and on this machine,
#: anchored to it.
SELF = "self"
HERE = "local"

#: How a runtime was made: typed in field by field, or read off an ssh config.
TYPED = "typed"
IMPORTED = "imported"

#: What a runtime may be called: one path component, holding nothing a shell or a filesystem
#: reads as something else, which cannot climb out of the directory it names.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: What the file a runtime is written down in is called.
_HELD = "runtime.json"

#: What it was called when a runtime was an environment provider, read where it is still all
#: there is.
_WAS = "provider.json"

#: A host, a login or an ssh config alias: a word `ssh` takes as one, never read as an option.
_WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._%+-]*\Z")

#: A jump host, which may be several, as `ProxyJump` takes them.
_JUMP = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._%+@:,\[\]-]*\Z")

#: An ssh_config keyword, as `-o` takes one.
_KEYWORD = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")

#: The options an ssh runtime has a field for, which are set there rather than as options.
_FIELDS = {
    "hostname": "host",
    "user": "user",
    "port": "port",
    "identityfile": "identity_file",
    "proxyjump": "proxy_jump",
}

#: The largest port there is.
_PORT_MAX = 65535

#: The fields a runtime holds as a mapping of one string to another.
_MAPPINGS = ("options", "nodes")


def _text(value: str, what: str) -> str:
    """A value that is one line of text holding no double quote, or ValueError.

    Not a quote because ssh reads its options' quoting with them, and there is no way to
    tell it one that is part of a value.
    """
    if set(value) & set('\n\r\0"'):
        raise ValueError(f"{what} {value!r} cannot contain newlines or quotes")
    return value


def _here(value: str, what: str) -> str:
    """A path on this machine with its `~` or `~user` expanded, or ValueError.

    `Path.expanduser` raises `RuntimeError` for a `~user` there is no such user for, which
    would crash whatever reads the runtime; that is a value it cannot take instead.
    """
    expanded = os.path.expanduser(value)  # noqa: PTH111 -- which raises for one
    if expanded.startswith("~"):
        raise ValueError(f"{what} {value!r}: home directory not found")
    return expanded


def _workdir(value: str) -> str:
    """A default workdir: absolute, or under the login's home, or none at all."""
    _text(value, "the workdir")
    if value and value != "~" and not value.startswith(("/", "~/")):
        raise ValueError(f"the workdir {value!r} must be absolute or under ~/")
    return value


def _falls_back(backend: str, name: str, fallback: tuple[str, ...]) -> None:
    """Refuses a fallback list that is not one: each a `<backend>:<name>` once, never itself.

    Whether the runtimes it names are there is asked when one is fallen back to, not here: a
    runtime taken away is one an environment cannot be held on, which is a refusal like any
    other, and the list may well be written before the runtimes it names are.

    Raises:
      ValueError: For an entry that names no backend, or a name no runtime may have; for one
        named twice; and for the runtime itself.
    """
    seen: set[str] = set()
    for one in fallback:
        kind, colon, called = one.partition(":")
        if not colon or kind not in BACKENDS or not _NAMED.match(called):
            raise ValueError(
                f"{name}: fallback {one!r} must be <backend>:<name>, the backend "
                f"one of {', '.join(BACKENDS)}"
            )
        if (kind, called) == (backend, name):
            raise ValueError(f"{name}: a runtime cannot fall back to itself")
        if one in seen:
            raise ValueError(f"{name}: fallback {one} is named twice")
        seen.add(one)


def _named(name: str) -> str:
    if not _NAMED.match(name):
        raise ValueError(
            f"invalid runtime name {name!r}: must start with a "
            "letter or digit and contain only letters, digits, dots, dashes, "
            "and underscores"
        )
    return name


def affine(entry: str) -> tuple[str, str] | None:
    """One entry of an affinity, read: the runtime it names, if it names one.

    Args:
      entry: As an affinity holds it: `self`, `local`, or `<backend>:<name>`.

    Returns:
      `(backend, name)` for a runtime, None for one of the two places that are not one.

    Raises:
      ValueError: For anything else.
    """
    if entry in (SELF, HERE):
        return None
    backend, colon, name = entry.partition(":")
    if not colon or backend not in BACKENDS or not _NAMED.match(name):
        raise ValueError(
            f"{entry!r} is not where a harness runs: {SELF}, {HERE} or "
            f"<{'|'.join(BACKENDS)}>:<runtime name>"
        )
    return backend, name


def _affinity(runtime: Runtime) -> None:
    """Refuses an affinity that is not one.

    An entry that does not read, one named twice, or the runtime itself -- which is its own
    machine, and so :data:`SELF` rather than a runtime the harness is put on beside it.

    Raises:
      ValueError: For one of those.
    """
    for at, entry in enumerate(runtime.affinity):
        try:
            named = affine(entry)
        except ValueError as why:
            raise ValueError(f"{runtime.name}: {why}") from None
        if entry in runtime.affinity[:at]:
            raise ValueError(f"{runtime.name}: {entry} is in its affinity twice")
        if named == (runtime.backend, runtime.name):
            raise ValueError(
                f"{runtime.name}: its affinity names itself; {SELF} is its own machine"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class SSHRuntime:
    """A host reached over ssh, and everything `ssh` is to be told to reach it.

    Every field that is set is passed to `ssh`, on top of whatever the user's own config says
    for that destination -- and before it, so that what is written here wins.

    Attributes:
      name: What it is called, which is what `-e <role>=ssh@<name>/<workdir>` names.
      host: The machine: a host name or an address. With an alias as well, what the alias is
        pointed at instead of the machine the config names (`HostName`).
      user: Who to log in as, or "" for whoever the config or this machine says.
      port: The port to dial, or 0 for the config's or 22.
      identity_file: The key to log in with (`IdentityFile`), by path; its contents are never
        read here.
      proxy_jump: The host or hosts it is reached through (`ProxyJump`).
      options: Anything else, as `-o KEYWORD=VALUE`.
      alias: The `Host` of an ssh config it was imported as, which `ssh` then resolves through
        that config -- so the config goes on being what it says.
      config: The ssh config file it was imported from, where that is not the user's own:
        `ssh` is told to read it instead (`-F`).
      workdir: Where an `-e` naming it with no workdir works.
      fallback: The runtimes an environment an `-e` puts here moves to, in order, where this
        one cannot hold it -- each `<backend>:<name>`, as `ssh:gpu2` or `docker:box`.
      made: How it was made: :data:`TYPED` or :data:`IMPORTED`.
      affinity: Where the harness of an agent working on it runs, in the order tried: the
        next only where the one before has no room. See :func:`affine` for an entry.
    """

    backend: ClassVar[str] = SSH

    name: str
    host: str = ""
    user: str = ""
    port: int = 0
    identity_file: str = ""
    proxy_jump: str = ""
    options: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    alias: str = ""
    config: str = ""
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    affinity: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _named(self.name)
        _affinity(self)
        if not self.host and not self.alias:
            raise ValueError(
                f"{self.name}: an ssh host requires a hostname or an alias"
            )
        for value, what in (
            (self.host, "host"),
            (self.alias, "alias"),
            (self.user, "user"),
        ):
            if value and not _WORD.match(value):
                raise ValueError(f"{self.name}: invalid ssh {what} {value!r}")
        if not 0 <= self.port <= _PORT_MAX:
            raise ValueError(f"{self.name}: invalid port {self.port}")
        if self.proxy_jump and not _JUMP.match(self.proxy_jump):
            raise ValueError(f"{self.name}: invalid jump host {self.proxy_jump!r}")
        _text(self.identity_file, "the identity file")
        _text(self.config, "the config file")
        _workdir(self.workdir)
        _falls_back(SSH, self.name, self.fallback)
        if self.made not in (TYPED, IMPORTED):
            raise ValueError(
                f"{self.name}: made must be {TYPED} or {IMPORTED}, not {self.made!r}"
            )
        for key, value in self.options.items():
            if not _KEYWORD.match(key) or key == "F":
                raise ValueError(f"{self.name}: invalid ssh option {key!r}")
            if key.lower() in _FIELDS:
                raise ValueError(
                    f"{self.name}: {key} must be set with "
                    f"{_FIELDS[key.lower()]}, not as an option"
                )
            if not value:
                raise ValueError(f"{self.name}: option {key} cannot be empty")
            _text(value, f"the option {key}")

    @property
    def at(self) -> Path:
        """The directory it is kept in."""
        return where(SSH, self.name)

    def destination(self) -> str:
        """What `ssh` is given to connect to: the alias where there is one, else the host."""
        return self.alias or self.host

    def login(self) -> str:
        """The destination with the user in front, as `ssh` and a URL both take it."""
        return f"{self.user}@{self.destination()}" if self.user else self.destination()

    def settings(self) -> tuple[tuple[str, str], ...]:
        """Everything `ssh` is told besides the login, the port and the destination.

        Returns:
          `(KEYWORD, VALUE)` pairs as :attr:`hmz.coganchor.transport.Target.options` holds
          them: the config file as `F`, then the fields that are options, then the options.

        Raises:
          ValueError: For a config file under a home there is no longer any of.
        """
        said: list[tuple[str, str]] = []
        if self.config:
            said.append(("F", _here(self.config, "the config file")))
        if self.alias and self.host:
            said.append(("HostName", self.host))
        if self.identity_file:
            said.append(("IdentityFile", self.identity_file))
        if self.proxy_jump:
            said.append(("ProxyJump", self.proxy_jump))
        said.extend(self.options.items())
        return tuple(said)

    def target(self) -> str:
        """The coganchor target that reaches it: `ssh://[user@]dest[:port][?KEYWORD=VALUE&...]`."""
        from hmz.coganchor.transport import Target

        return Target(
            "ssh",
            host=self.login(),
            port=self.port,
            options=self.settings(),
        ).describe()

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": SSH, **_fields(self)}


@dataclass(frozen=True, slots=True, kw_only=True)
class DockerRuntime:
    """A docker daemon a container may be started on, and what it may hand out.

    Attributes:
      name: What it is called, which is what an environment on it names.
      endpoint: Where the daemon is: `local` for whatever `docker` here reaches,
        `unix:///path.sock`, `tcp://host:port`, `ssh://[user@]host[:port]`,
        `ssh:<name>` for the stored ssh runtime of that name, or `context:<name>` for a
        docker context.
      tls_dir: For `tcp://`, the directory holding `ca.pem`, `cert.pem` and `key.pem`.
      image: What a container is started from where the flow says nothing.
      runtime: The OCI runtime to start a container under, e.g. `nvidia`, or "" for the
        daemon's default.
      run_args: What else `docker run` is told.
      cpus: How many CPUs it may hand out, or 0 for as many as it has.
      memory: How many bytes of memory, or 0 for as many as it has.
      gpus: The GPUs it may hand out, by device id -- `("0", "1")` -- or none.
      gpu_memory: How many bytes each of those GPUs has, or 0 for unsaid.
      max_containers: How many containers it may run at once, or 0 for no limit.
      workdir: Where an `-e` naming it with no workdir works.
      fallback: The runtimes an environment an `-e` puts here moves to, in order, where this
        one cannot hold it -- each `<backend>:<name>`.
      made: How it was made, which is :data:`TYPED`.
      affinity: Where the harness of an agent working on it runs, in the order tried: the
        next only where the one before has no room. See :func:`affine` for an entry.
    """

    backend: ClassVar[str] = DOCKER

    name: str
    endpoint: str = "local"
    tls_dir: str = ""
    image: str = ""
    runtime: str = ""
    run_args: tuple[str, ...] = ()
    cpus: float = 0.0
    memory: int = 0
    gpus: tuple[str, ...] = ()
    gpu_memory: int = 0
    max_containers: int = 0
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    affinity: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _named(self.name)
        _affinity(self)
        _endpoint(self.endpoint)
        if self.tls_dir and not self.endpoint.startswith("tcp://"):
            raise ValueError(f"{self.name}: TLS certificates require a tcp:// endpoint")
        _text(self.tls_dir, "the TLS directory")
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: invalid image {self.image!r}")
        if self.runtime and not _WORD.match(self.runtime):
            raise ValueError(f"{self.name}: invalid OCI runtime {self.runtime!r}")
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: argument {said!r} cannot contain newlines"
                )
        for gpu in self.gpus:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", gpu):
                raise ValueError(f"{self.name}: invalid GPU id {gpu!r}")
        if len(set(self.gpus)) != len(self.gpus):
            raise ValueError(f"{self.name}: duplicate GPU specified")
        for amount, what in (
            (self.cpus, "CPUs"),
            (self.memory, "memory"),
            (self.gpu_memory, "GPU memory"),
            (self.max_containers, "containers"),
        ):
            if amount < 0:
                raise ValueError(f"{self.name}: {what} cannot be negative: {amount}")
        _workdir(self.workdir)
        _falls_back(DOCKER, self.name, self.fallback)
        if self.made != TYPED:
            raise ValueError(
                f"{self.name}: made must be {TYPED} for a docker host, not {self.made!r}"
            )

    @property
    def at(self) -> Path:
        """The directory it is kept in."""
        return where(DOCKER, self.name)

    def daemon(self) -> Endpoint:
        """The daemon this one is, as every `docker` for it is pointed at it.

        Raises:
          ValueError: For `ssh:<name>` naming no stored ssh runtime.
        """
        return daemon_of(self.endpoint, self.tls_dir)

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": DOCKER, **_fields(self)}


#: What a placement constraint is, as `docker service create --constraint` takes one: an
#: attribute of a node, compared to a value.
_CONSTRAINT = re.compile(r"[A-Za-z][A-Za-z0-9._/-]*\s*(==|!=)\s*\S.*\Z")

#: What a generic resource is called, as a node advertises one: `NVIDIA-GPU`, `GPU`.
_RESOURCE = re.compile(r"[A-Za-z][A-Za-z0-9._-]*\Z")


@dataclass(frozen=True, slots=True, kw_only=True)
class SwarmRuntime:
    """A docker swarm a service may be created on, and what its tasks may hold of it.

    Every environment on it is a service of one task, which the swarm's scheduler places on
    whichever node has room for what the role reserves -- and which is then reached through
    the docker daemon of that node: the manager's own where the task landed on the manager,
    else over ssh to the node.

    Attributes:
      name: What it is called, which is what an environment on it names.
      endpoint: Where a manager of the swarm is, spelled as :attr:`DockerRuntime.endpoint`
        is: `local` for a swarm this machine manages, else the daemon of one that does.
      tls_dir: For `tcp://`, the directory holding `ca.pem`, `cert.pem` and `key.pem`.
      image: What a task is started from where the flow says nothing. Every node it may land
        on has to be able to pull it.
      run_args: What else `docker service create` is told.
      cpus: How many CPUs its tasks may reserve all told, or 0 for as many as the swarm's
        nodes have room for.
      memory: How many bytes of memory, likewise.
      gpu_resource: The generic resource its nodes advertise their GPUs as -- `NVIDIA-GPU` --
        which a role asking for GPUs reserves that many of; "" where it hands out none.
      constraints: Where its tasks may be placed, as `--constraint` takes each:
        `node.labels.gpu==true`, `node.role!=manager`.
      max_tasks: How many tasks it may run at once, or 0 for no limit.
      nodes: How a node is reached, by its host name, where it is not `ssh://<its address>`:
        the name of a saved ssh runtime, or an ssh destination `[user@]host[:port]`.
      workdir: Where an `-e` naming it with no workdir works -- a directory every node it
        may land on has, at the same path.
      fallback: The runtimes an environment an `-e` puts here moves to, in order, where this
        one cannot hold it -- each `<backend>:<name>`.
      made: How it was made, which is :data:`TYPED`.
      affinity: Where the harness of an agent working on it runs, in the order tried: the
        next only where the one before has no room. See :func:`affine` for an entry.
    """

    backend: ClassVar[str] = SWARM

    name: str
    endpoint: str = "local"
    tls_dir: str = ""
    image: str = ""
    run_args: tuple[str, ...] = ()
    cpus: float = 0.0
    memory: int = 0
    gpu_resource: str = ""
    constraints: tuple[str, ...] = ()
    max_tasks: int = 0
    nodes: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    affinity: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _named(self.name)
        _affinity(self)
        _endpoint(self.endpoint)
        if self.tls_dir and not self.endpoint.startswith("tcp://"):
            raise ValueError(f"{self.name}: TLS certificates require a tcp:// endpoint")
        _text(self.tls_dir, "the TLS directory")
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: invalid image {self.image!r}")
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: argument {said!r} cannot contain newlines"
                )
        for amount, what in (
            (self.cpus, "CPUs"),
            (self.memory, "memory"),
            (self.max_tasks, "tasks"),
        ):
            if amount < 0:
                raise ValueError(f"{self.name}: {what} cannot be negative: {amount}")
        if self.gpu_resource and not _RESOURCE.match(self.gpu_resource):
            raise ValueError(
                f"{self.name}: invalid generic resource {self.gpu_resource!r}"
            )
        for constraint in self.constraints:
            if not _CONSTRAINT.match(constraint) or set(constraint) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: invalid constraint {constraint!r}: expected "
                    "<attribute>==<value> or <attribute>!=<value>"
                )
        for node, via in self.nodes.items():
            if not _WORD.match(node):
                raise ValueError(f"{self.name}: invalid node host name {node!r}")
            if not _NAMED.match(via) and not _destination(via):
                raise ValueError(
                    f"{self.name}: node {node}: {via!r} is neither a saved ssh host "
                    "nor [user@]host[:port]"
                )
        _workdir(self.workdir)
        _falls_back(SWARM, self.name, self.fallback)
        if self.made != TYPED:
            raise ValueError(
                f"{self.name}: made must be {TYPED} for a docker swarm, not {self.made!r}"
            )

    @property
    def at(self) -> Path:
        """The directory it is kept in."""
        return where(SWARM, self.name)

    def daemon(self) -> Endpoint:
        """The manager's daemon, as every `docker` for the swarm is pointed at it.

        Raises:
          ValueError: For `ssh:<name>` naming no stored ssh runtime.
        """
        return daemon_of(self.endpoint, self.tls_dir)

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": SWARM, **_fields(self)}


def node_of(via: str) -> str:
    """The daemon endpoint a swarm node is reached by, as a runtime spells one.

    Args:
      via: As :attr:`SwarmRuntime.nodes` holds it: a saved ssh runtime's name, or an ssh
        destination `[user@]host[:port]`.

    Returns:
      `ssh:<name>` for a saved ssh runtime that is there, else `ssh://<destination>` --
      which :func:`daemon_of` reads.

    Raises:
      ValueError: For one that is neither.
    """
    if _NAMED.match(via) and find(SSH, via) is not None:
        return f"ssh:{via}"
    if not _destination(via):
        raise ValueError(f"{via!r} is neither a saved ssh host nor [user@]host[:port]")
    return f"ssh://{via}"


def _destination(via: str) -> bool:
    """Whether something is an ssh destination a docker endpoint may be: `[user@]host[:port]`."""
    try:
        _endpoint(f"ssh://{via}")
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True, kw_only=True)
class AppleContainerRuntime:
    """This Mac's Apple containers, and how much of the Mac they may have between them.

    Apple's `container` runs each container as a small Linux virtual machine of its own, on
    this Mac and no other: there is no daemon elsewhere to name, and no GPU to hand out.

    Attributes:
      name: What it is called, which is what an environment on it names.
      image: What a container is started from where the flow says nothing.
      run_args: What else `container run` is told.
      cpus: How many CPUs its containers may be given all told, or 0 for as many as the Mac
        has.
      memory: How many bytes of memory, likewise.
      max_containers: How many containers it may run at once, or 0 for no limit.
      workdir: Where an `-e` naming it with no workdir works.
      fallback: The runtimes an environment an `-e` puts here moves to, in order, where this
        one cannot hold it -- each `<backend>:<name>`.
      made: How it was made, which is :data:`TYPED`.
      affinity: Where the harness of an agent working on it runs, in the order tried: the
        next only where the one before has no room. See :func:`affine` for an entry.
    """

    backend: ClassVar[str] = APPLE_CONTAINER

    name: str
    image: str = ""
    run_args: tuple[str, ...] = ()
    cpus: float = 0.0
    memory: int = 0
    max_containers: int = 0
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    affinity: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _named(self.name)
        _affinity(self)
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: invalid image {self.image!r}")
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: argument {said!r} cannot contain newlines"
                )
        for amount, what in (
            (self.cpus, "CPUs"),
            (self.memory, "memory"),
            (self.max_containers, "containers"),
        ):
            if amount < 0:
                raise ValueError(f"{self.name}: {what} cannot be negative: {amount}")
        _workdir(self.workdir)
        _falls_back(APPLE_CONTAINER, self.name, self.fallback)
        if self.made != TYPED:
            raise ValueError(
                f"{self.name}: made must be {TYPED} for Apple containers, "
                f"not {self.made!r}"
            )

    @property
    def at(self) -> Path:
        """The directory it is kept in."""
        return where(APPLE_CONTAINER, self.name)

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": APPLE_CONTAINER, **_fields(self)}


#: One runtime, of whichever backend.
type Runtime = SSHRuntime | DockerRuntime | SwarmRuntime | AppleContainerRuntime


def _fields(runtime: Runtime) -> dict[str, Any]:
    """Every field of one, as JSON holds it."""
    held: dict[str, Any] = {}
    for one in dataclasses.fields(runtime):
        value: object = getattr(runtime, one.name)
        if isinstance(value, tuple):
            value = [str(each) for each in cast("tuple[object, ...]", value)]
        elif one.name in _MAPPINGS:
            value = dict(cast("Mapping[str, str]", value))
        held[one.name] = value
    return held


# ------------------------------------------------------------------------ docker endpoints


def _endpoint(endpoint: str) -> str:
    """An endpoint as a runtime spells it, checked: one `Endpoint` reads, or `ssh:<name>`.

    Raises:
      ValueError: For one that is neither.
    """
    from hmz.coganchor.transport import Endpoint

    if endpoint.startswith("ssh:") and not endpoint.startswith("ssh://"):
        if _NAMED.match(endpoint[len("ssh:") :]):
            return endpoint
    elif endpoint.startswith("ssh://"):
        # A word ssh reads as a login or a host, never as an option, and nothing after it:
        # what else a daemon's host needs is said by an ssh runtime, `ssh:<name>`.
        login, _, at = endpoint[len("ssh://") :].rpartition("@")
        host, _, port = at.partition(":")
        if (
            _WORD.match(host)
            and (not login or _WORD.match(login))
            and (not port or (port.isdigit() and 0 < int(port) <= _PORT_MAX))
        ):
            return endpoint
    else:
        try:
            read = Endpoint.parse(endpoint)
        except ValueError:
            pass
        else:
            port = (
                read.host.rpartition(":")[2] if read.host.startswith("tcp://") else ""
            )
            if (
                endpoint
                and "?" not in endpoint
                and (not port or 0 < int(port) <= _PORT_MAX)
                and (not read.context or _NAMED.match(read.context))
            ):
                return endpoint
    raise ValueError(
        f"{endpoint!r} is not a docker endpoint: local, unix:///PATH, "
        "tcp://HOST:PORT, ssh://[USER@]HOST[:PORT], ssh:<ssh host> or "
        "context:<docker context>"
    )


def daemon_of(endpoint: str, tls_dir: str = "") -> Endpoint:
    """The daemon an endpoint names, as a runtime spells it, for `docker` to be pointed at.

    What a runtime adds to :class:`~hmz.coganchor.transport.Endpoint`, which is the one place
    an endpoint becomes a command line: its certificates beside it rather than in it, and
    `ssh:<name>` for the stored ssh runtime a daemon's host is reached as -- dialled with
    everything that runtime says.

    Args:
      endpoint: As :attr:`DockerRuntime.endpoint` spells it.
      tls_dir: For `tcp://`, the directory of its certificates, or "" for none.

    Returns:
      The daemon.

    Raises:
      ValueError: For an endpoint that is none of them, `ssh:<name>` naming no stored
        ssh runtime, or certificates under a home there is none of.
    """
    from hmz.coganchor.transport import Endpoint

    _endpoint(endpoint)
    if not endpoint.startswith("ssh:") or endpoint.startswith("ssh://"):
        certs = (
            f"?tls={Path(_here(tls_dir, 'the TLS directory')).absolute()}"
            if tls_dir
            else ""
        )
        return Endpoint.parse(endpoint + certs)
    name = endpoint[len("ssh:") :]
    found = find(SSH, name)
    if found is None:
        raise ValueError(f"{endpoint}: ssh host {name!r} not found")
    found = cast("SSHRuntime", found)
    port = f":{found.port}" if found.port else ""
    return Endpoint(host=f"ssh://{found.login()}{port}", options=found.settings())


# ---------------------------------------------------------------------------- the store


def under() -> Path:
    """Where every runtime is kept, whether or not anything is.

    Where they were kept when they were environment providers is moved here the first time
    this is asked and nothing is here yet: in one rename, so that a second asking at the same
    moment finds either all of them here or none moved.
    """
    at = home() / "runtimes"
    if not at.exists():
        with contextlib.suppress(OSError):  # nothing to move, or moved a moment ago
            (home() / "env-providers").rename(at)
    return at


def where(backend: str, name: str) -> Path:
    """The directory one runtime is kept in.

    Args:
      backend: :data:`SSH`, :data:`DOCKER`, :data:`SWARM` or :data:`APPLE_CONTAINER`.
      name: What the runtime is called.

    Returns:
      The path, whether or not anything is there yet.

    Raises:
      ValueError: If the backend is not one of them, or the name is not one a runtime may
        have.
    """
    if backend not in BACKENDS:
        raise ValueError(f"{backend!r} is not a runtime backend: {', '.join(BACKENDS)}")
    return under() / backend / _named(name)


def new(backend: str, name: str, **fields: Any) -> Runtime:
    """One runtime, checked, and written nowhere.

    Args:
      backend: :data:`SSH`, :data:`DOCKER`, :data:`SWARM` or :data:`APPLE_CONTAINER`.
      name: What it is called.
      **fields: The rest of it, by field -- as :meth:`SSHRuntime.held` writes them, lists and
        numbers as JSON has them.

    Returns:
      It.

    Raises:
      ValueError: If it is not a runtime of that backend: a field it has not got, or a
        value it cannot take.
    """
    if backend not in BACKENDS:
        raise ValueError(f"{backend!r} is not a runtime backend: {', '.join(BACKENDS)}")
    kind: type[Runtime] = {
        SSH: SSHRuntime,
        DOCKER: DockerRuntime,
        SWARM: SwarmRuntime,
        APPLE_CONTAINER: AppleContainerRuntime,
    }[backend]
    known = {one.name: one for one in dataclasses.fields(kind)}
    given: dict[str, Any] = {"name": name}
    for key, value in fields.items():
        if key not in known or key == "name":
            raise ValueError(f"{name}: unknown {backend} host setting {key!r}")
        given[key] = _typed(key, known[key].default, value, name)
    return kind(**given)


def _typed(key: str, default: object, value: object, name: str) -> object:
    """One field's value, as the field holds it.

    Raises:
      ValueError: For one of another type.
    """
    wrong = ValueError(f"{name}: {key} cannot be {value!r}")
    if key in _MAPPINGS:
        if not isinstance(value, dict):
            raise wrong
        return {str(k): str(v) for k, v in cast("dict[Any, Any]", value).items()}
    if isinstance(default, tuple):
        if not isinstance(value, (list, tuple)):
            raise wrong
        return tuple(str(one) for one in cast("Iterable[Any]", value))
    if isinstance(value, bool):
        raise wrong
    if isinstance(default, float):
        if not isinstance(value, (int, float)):
            raise wrong
        return float(value)
    if isinstance(default, int):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if not isinstance(value, int):
            raise wrong
        return value
    if not isinstance(value, str):
        raise wrong
    return value


def runtimes(backend: str = "") -> list[Runtime]:
    """Every runtime there is, or every one of a backend.

    Args:
      backend: :data:`SSH`, :data:`DOCKER`, :data:`SWARM`, :data:`APPLE_CONTAINER`, or ""
        for every one.

    Returns:
      One apiece, by backend and then by name. A directory holding nothing readable, or
      under a name no runtime could be made under, is not one and is left out.
    """
    held: list[Runtime] = []
    for kind in BACKENDS:
        if backend and kind != backend:
            continue
        try:
            names = sorted(
                one.name for one in (under() / kind).iterdir() if one.is_dir()
            )
        except OSError:
            continue
        held.extend(
            one
            for named in names
            if _NAMED.match(named) and (one := _read(kind, named)) is not None
        )
    return held


def find(backend: str, name: str) -> Runtime | None:
    """The runtime of a backend called this, or None -- for a name none could have too."""
    if backend not in BACKENDS or not _NAMED.match(name):
        return None
    return _read(backend, name)


def fallbacks(backend: str, name: str) -> tuple[tuple[str, str], ...]:
    """What the runtime of a backend called this falls back to, each as `(backend, name)`.

    Its own list and nothing further: a runtime fallen back to is not walked on down its own,
    which is what keeps a chain from going round in a circle, or on to somewhere nobody who
    wrote the first list ever named.

    Returns:
      The runtimes, in the order they are to be tried; none for a runtime with no list, or
      none under that name.
    """
    found = find(backend, name)
    if found is None:
        return ()
    return tuple(
        (kind, called)
        for kind, _, called in (one.partition(":") for one in found.fallback)
    )


#: How what is kept spells an `-e`, written beside it: `2` since an `@` is written before a
#: provider alone. What has no such mark was kept before, and is read through
#: :func:`respelled` -- and only that: `ssh@gpu/x` kept since is the runtime `gpu` whatever
#: becomes of it, where kept before it was the host `ssh` was handed if nothing was saved.
SPELLING = 2


def respelled(spec: str) -> str:
    """An `-e` kept from before an `@` was a provider's alone, as `-e` spells it now.

    Which turns on what is saved here. `ssh@gpu/x` is the runtime `gpu` where one is written
    down under that name -- read or not -- and otherwise the host `ssh` was handed, which `-e`
    takes in brackets now: `ssh@[gpu]/x`. `docker@local/x` and `swarm@local/x` are docker's
    default here and the swarm this machine manages, `docker/x` and `swarm/x`, unless a
    runtime of theirs is saved as `local`, which was taken first. `local@/x` is `local/x`.
    For what was kept before :data:`SPELLING` was written beside it -- settings, and the record
    of a run -- and for what a machine calls itself; never for a line, which is refused saying
    the same.

    Args:
      spec: What followed `<role>=`.

    Returns:
      The spec as `-e` takes it now: the one given wherever it already was, or is none.
    """
    said = spec.strip()
    cut = min((at for at in (said.find("@"), said.find("/")) if at >= 0), default=-1)
    if cut < 0 or said[cut] != "@":
        return spec  # no provider, which is no `@` to have been read the old way
    backend = said[:cut].strip()
    provider, slash, workdir = said[cut + 1 :].partition("/")
    provider, at = provider.strip(), slash + workdir
    if backend == "local" and not provider and at:
        return f"{backend}{at}"
    if backend not in BACKENDS or not provider or provider.startswith("["):
        return spec
    try:
        if where(backend, provider).exists():
            return spec
    except ValueError:
        pass  # a name no runtime may have, which a destination like `me@box` is
    if backend == SSH:
        return f"{backend}@[{provider}]{at}"
    return f"{backend}{at}" if provider == "local" else spec


def _read(backend: str, name: str) -> Runtime | None:
    """One runtime read back, or None where nothing readable is there.

    The backend and the name are where it is kept, whatever the file says: the place is the
    answer, and the file only describes it.
    """
    kept = under() / backend / name
    try:
        held = kept / _HELD if (kept / _HELD).exists() else kept / _WAS
        said = json.loads(held.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(said, dict):
        return None
    fields = {
        str(key): value
        for key, value in cast("dict[Any, Any]", said).items()
        if key not in ("backend", "name")
    }
    try:
        return new(backend, name, **fields)
    except ValueError:
        return None


def add(runtime: Runtime) -> Runtime:
    """Writes a new runtime down.

    Raises:
      ValueError: If there is one of that backend under that name already, or it names a
        path under a home there is none of.
      OSError: If it cannot be written.
    """
    if find(runtime.backend, runtime.name) is not None:
        raise ValueError(f"{runtime.backend} host {runtime.name!r} already exists")
    return write(runtime)


def write(runtime: Runtime) -> Runtime:
    """Writes a runtime down, whole, over whatever was under its name.

    Returns:
      It, as it is now written down.

    Raises:
      ValueError: If it names a config file or certificates under a home there is none of,
        which would be a runtime nothing could reach. Refused here rather than where it is
        made, so that one written down while its home was there is still listed -- and
        checked, saying why -- once it has gone.
      OSError: If it cannot be written.
    """
    if isinstance(runtime, SSHRuntime):
        _here(runtime.config, "the config file")
    elif not isinstance(runtime, AppleContainerRuntime):
        _here(runtime.tls_dir, "the TLS directory")
    at = where(runtime.backend, runtime.name)
    _kept(at)
    _writes(at / _HELD, json.dumps(runtime.held(), indent=2) + "\n")
    (at / _WAS).unlink(missing_ok=True)
    return runtime


def remove(backend: str, name: str) -> bool:
    """Takes a runtime away.

    Returns:
      Whether there was one to take away.

    Raises:
      ValueError: If the backend or the name is not one there could be.
    """
    at = where(backend, name)
    if not at.is_dir():
        return False
    shutil.rmtree(at)
    return True


def _kept(at: Path) -> None:
    """Makes a directory and every one above it that is missing, each this user's alone."""
    made: list[Path] = []
    for one in (at, *at.parents):
        if one.exists():
            break
        made.append(one)
    for one in reversed(made):
        one.mkdir(exist_ok=True)
        one.chmod(0o700)  # set rather than asked for, which the umask would take from


def _writes(at: Path, said: str, mode: int = 0o600) -> None:
    """Writes a file whole, readable by its owner alone from the moment it exists."""
    atomic.writes(at, said, mode=mode)


# ------------------------------------------------------------------------ an ssh config


def imports(
    config: str | os.PathLike[str] | None = None,
    names: Iterable[str] | None = None,
    *,
    update: bool = False,
) -> list[SSHRuntime]:
    """Writes an ssh runtime down for each host an ssh config names.

    Each is called after its `Host`, with anything no runtime name may hold made a dash,
    and holds the alias rather than what it resolves to: `ssh` goes on reading the config
    for it, so the config goes on being what it says.

    Args:
      config: The config file, or None for the user's own.
      names: The hosts to import, by their `Host`, or None for every one.
      update: Whether to write over a runtime of that name an import made -- keeping the
        workdir and the fallback it was given -- rather than leave it be. One typed in is
        never written over.

    Returns:
      The runtimes written, in the order the config names them.

    Raises:
      ValueError: If `names` names a host the config does not, or one that cannot be a
        runtime: under no name, under the name of another host named, or -- to be updated --
        over one typed in.
      OSError: If one cannot be written.
    """
    from . import sshconfig

    found = sshconfig.aliases(config)
    wanted = found if names is None else list(names)
    if missing := [one for one in wanted if one not in found]:
        raise ValueError(f"ssh config has no host {', '.join(missing)}")
    own = config is not None and Path(_here(str(config), "the config")).resolve() != (
        sshconfig.default().resolve()
    )
    # Every one made before any is written, so that one refused writes none of them.
    making: list[SSHRuntime] = []
    seen: dict[str, str] = {}
    for alias in wanted:
        name = re.sub(r"[^A-Za-z0-9._-]", "-", alias).lstrip("._-")
        already = find(SSH, name) if name else None
        # A runtime somebody typed in is theirs, and an import does not write over it; nor
        # does a second host that would be called what the first one already is.
        if not name or name in seen:
            why = f"{seen[name]} is imported as {name}" if name else "it has no name"
        elif update and already is not None and already.made != IMPORTED:
            why = f"{name} was typed in, and an import does not write over it"
        else:
            why = ""
        if why:
            if names is not None:
                raise ValueError(f"{alias} cannot be imported: {why}")
            continue
        seen[name] = alias
        if already is not None and not update:
            continue
        try:
            runtime = SSHRuntime(
                name=name,
                alias=alias,
                config=str(Path(_here(str(config), "the config")).resolve())
                if own and config
                else "",
                workdir=already.workdir if already is not None else "",
                fallback=already.fallback if already is not None else (),
                made=IMPORTED,
                affinity=already.affinity if already is not None else (),
            )
        except ValueError:
            if names is not None:
                raise
            continue  # a host ssh reads and a runtime cannot hold, left where it is
        making.append(runtime)
    return [cast("SSHRuntime", write(runtime)) for runtime in making]
