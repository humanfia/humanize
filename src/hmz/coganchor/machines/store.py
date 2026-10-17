"""The runtimes: the machines a flow's environments may be put on, written down under names.

A runtime is one machine something can be put on, named by what somebody called it rather than
by how it is reached: an ssh host with the login, port, key and jump host it takes, a docker
daemon with the resources it may hand out, a docker swarm whose manager schedules a task for
each environment onto whichever of its nodes has room, this Mac's Apple containers with the
share of it they may have, or the Slurm cluster this machine submits to, with the partition and
account a job for each environment is submitted under. A flow's environment is put on one
when an `-e` names it, and moved down the runtimes it falls back to where it cannot be held
there. One entry per runtime, under `runtimes: <backend>: <name>:` in humanize's settings,
beside everything else `/settings` sets.

Nothing here reaches a machine. What one is when it is asked is
:mod:`hmz.runtime.doing.runtimes`'s, and reading the user's ssh config is
:mod:`hmz.coganchor.machines.sshconfig`'s; this is only the answer to "which ones are there, and
what is in each".
"""

from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz.coganchor import settings

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from hmz.coganchor.transport import Endpoint

__all__ = [
    "APPLE_CONTAINER",
    "BACKENDS",
    "DOCKER",
    "ENV",
    "HERE",
    "IMPORTED",
    "SLURM",
    "SPELLING",
    "SSH",
    "SWARM",
    "TYPED",
    "AppleContainerRuntime",
    "DockerRuntime",
    "Runtime",
    "SSHRuntime",
    "SlurmRuntime",
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
    "saved",
    "write",
]

#: The backends a runtime may be for, by the name `-e` gives each.
SSH = "ssh"
DOCKER = "docker"
SWARM = "swarm"
APPLE_CONTAINER = "apple-container"
SLURM = "slurm"
BACKENDS = (SSH, DOCKER, SWARM, APPLE_CONTAINER, SLURM)

#: The two places a harness may be put that are not a runtime of their own, as a runtime's
#: harness setting names them: natively on the machine of the runtime the work is on, and on
#: this machine, anchored to it.
ENV = "env"
HERE = "local"

#: How a runtime was made: typed in field by field, or read off an ssh config.
TYPED = "typed"
IMPORTED = "imported"

#: What a runtime may be called: one path component, holding nothing a shell or a filesystem
#: reads as something else, which cannot climb out of the directory it names.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: Where in humanize's settings the runtimes are written down, by backend and then by name.
_HELD = "runtimes"

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

#: What the name of a container or a service a runtime brings up may start with in place of
#: humanize's own: one word of letters, digits, dashes and underscores, from a letter or a
#: digit to a letter or a digit -- which a swarm takes in a service's name, as docker does in
#: a container's.
_PREFIX = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?\Z")

#: How long a name prefix may be: what the 63 characters a swarm takes in a service's name leave
#: once the dash and the 8 hex digits every name ends with are added.
_PREFIX_MAX = 63 - len("-01234567")

#: A container as docker names one, by its name or its id.
_CONTAINER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")

#: Who a command in a container runs as: the numeric `UID[:GID]` docker's `-u` takes.
_EXEC_USER = re.compile(r"[0-9]+(?::[0-9]+)?\Z")

#: What a variable a command in a container is given may be called.
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


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


def _prefixed(name: str, prefix: str) -> None:
    """Refuses a name prefix that is not one, or that leaves no room for the rest of a name.

    Raises:
      ValueError: For one that :data:`_PREFIX` does not match, or one longer than
        :data:`_PREFIX_MAX`.
    """
    if prefix and not _PREFIX.match(prefix):
        raise ValueError(
            f"{name}: invalid name prefix {prefix!r}: letters, digits, dashes and "
            "underscores, starting and ending with a letter or a digit"
        )
    if len(prefix) > _PREFIX_MAX:
        raise ValueError(
            f"{name}: name prefix {prefix!r} is longer than {_PREFIX_MAX} characters: "
            "with a dash and 8 hex digits after it, a swarm service's name would be "
            "longer than 63"
        )


def _named(name: str) -> str:
    if not _NAMED.match(name):
        raise ValueError(
            f"invalid runtime name {name!r}: must start with a "
            "letter or digit and contain only letters, digits, dots, dashes, "
            "and underscores"
        )
    return name


def affine(entry: str) -> tuple[str, str] | None:
    """A harness setting, read: the runtime it names, if it names one.

    Args:
      entry: As a runtime holds it: `env`, `local`, or `<backend>:<name>`.

    Returns:
      `(backend, name)` for a runtime, None for one of the two places that are not one.

    Raises:
      ValueError: For anything else.
    """
    if entry in (ENV, HERE):
        return None
    backend, colon, name = entry.partition(":")
    if not colon or backend not in BACKENDS or not _NAMED.match(name):
        raise ValueError(
            f"{entry!r} is not where a harness runs: {ENV}, {HERE} or "
            f"<{'|'.join(BACKENDS)}>:<runtime name>"
        )
    return backend, name


def _harness(runtime: Runtime) -> None:
    """Refuses a harness setting that is not one.

    One that does not read, or the runtime itself -- which is its own machine, and so
    :data:`ENV` rather than a runtime the harness is put on beside it.

    Raises:
      ValueError: For one of those.
    """
    try:
        named = affine(runtime.harness)
    except ValueError as why:
        raise ValueError(f"{runtime.name}: {why}") from None
    if named == (runtime.backend, runtime.name):
        raise ValueError(
            f"{runtime.name}: its harness names itself; {ENV} is its own machine"
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
      harness: Where the harness of an agent working on it runs, and nowhere else: see
        :func:`affine`.
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
    harness: str = ENV

    def __post_init__(self) -> None:
        _named(self.name)
        _harness(self)
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
        """The file it is kept in."""
        return settings.where()

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
      container: A container already running on the daemon, by name or id, that every
        environment put here works in -- never started, counted, taken down or stopped
        here -- or "" for a container of its own per environment.
      exec_user: The `UID[:GID]` every command in an environment's container runs as, or ""
        for the container's own user.
      exec_env: `NAME=VALUE` variables every such command runs with.
      exec_wrapper: The words of a program in the container every such command runs under,
        which runs the command it is given after them.
      image: What a container is started from where the flow says nothing.
      runtime: The OCI runtime to start a container under, e.g. `nvidia`, or "" for the
        daemon's default.
      run_args: What else `docker run` is told.
      name_prefix: What the name of a container it starts begins with, before the role's
        name and 8 hex digits; "" for `humanize-<name>`.
      cpus: How many CPUs it may hand out, or 0 for as many as it has.
      memory: How many bytes of memory, or 0 for as many as it has.
      gpus: The GPUs it may hand out, by device id -- `("0", "1")` -- or none.
      gpu_memory: How many bytes each of those GPUs has, or 0 for unsaid.
      max_containers: How many containers it may run at once, or 0 for no limit.
      workdir: Where an `-e` naming it with no workdir works.
      fallback: The runtimes an environment an `-e` puts here moves to, in order, where this
        one cannot hold it -- each `<backend>:<name>`.
      made: How it was made, which is :data:`TYPED`.
      harness: Where the harness of an agent working on it runs, and nowhere else: see
        :func:`affine`.
    """

    backend: ClassVar[str] = DOCKER

    name: str
    endpoint: str = "local"
    tls_dir: str = ""
    container: str = ""
    exec_user: str = ""
    exec_env: tuple[str, ...] = ()
    exec_wrapper: tuple[str, ...] = ()
    image: str = ""
    runtime: str = ""
    run_args: tuple[str, ...] = ()
    name_prefix: str = ""
    cpus: float = 0.0
    memory: int = 0
    gpus: tuple[str, ...] = ()
    gpu_memory: int = 0
    max_containers: int = 0
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    harness: str = ENV

    def __post_init__(self) -> None:
        _named(self.name)
        _harness(self)
        _endpoint(self.endpoint)
        if self.tls_dir and not self.endpoint.startswith("tcp://"):
            raise ValueError(f"{self.name}: TLS certificates require a tcp:// endpoint")
        _text(self.tls_dir, "the TLS directory")
        _exec(self)
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: invalid image {self.image!r}")
        if self.runtime and not _WORD.match(self.runtime):
            raise ValueError(f"{self.name}: invalid OCI runtime {self.runtime!r}")
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: argument {said!r} cannot contain newlines"
                )
        _prefixed(self.name, self.name_prefix)
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
        """The file it is kept in."""
        return settings.where()

    def daemon(self) -> Endpoint:
        """The daemon this one is, as every `docker` for it is pointed at it.

        Raises:
          ValueError: For `ssh:<name>` naming no stored ssh runtime.
        """
        return daemon_of(self.endpoint, self.tls_dir)

    def exec_options(self) -> tuple[tuple[str, str], ...]:
        """What every `docker exec` into an environment's container is told besides it.

        Returns:
          `(KEY, VALUE)` pairs, as :attr:`hmz.coganchor.transport.Target.options` holds a
          docker target's: the user, then each variable, then each word of the wrapper.
        """
        return (
            *((("user", self.exec_user),) if self.exec_user else ()),
            *(("env", one) for one in self.exec_env),
            *(("exec", one) for one in self.exec_wrapper),
        )

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": DOCKER, **_fields(self)}


def _exec(runtime: DockerRuntime) -> None:
    """Refuses a docker runtime's container, or what is run in it, that is not one.

    A runtime naming a running container starts none, so what it would start one with or
    hand out of its daemon is refused beside it rather than left to say nothing.

    Raises:
      ValueError: For a container docker would not name so, an exec user that is not
        `UID[:GID]`, a variable that is not `NAME=VALUE`, an empty word of a wrapper, a
        value of more than one line; or, beside a container, anything to start one with.
    """
    name = runtime.name
    if runtime.container and not _CONTAINER.match(runtime.container):
        raise ValueError(f"{name}: invalid container {runtime.container!r}")
    if runtime.exec_user and not _EXEC_USER.match(runtime.exec_user):
        raise ValueError(f"{name}: exec user {runtime.exec_user!r} is not UID[:GID]")
    for said in runtime.exec_env:
        variable, equals, _ = said.partition("=")
        if not equals or not _VARIABLE.match(variable) or set(said) & set("\n\r\0"):
            raise ValueError(f"{name}: exec variable {said!r} is not NAME=VALUE")
    for said in runtime.exec_wrapper:
        if not said or set(said) & set("\n\r\0"):
            raise ValueError(
                f"{name}: exec wrapper word {said!r} is empty or two lines"
            )
    if runtime.container:
        starting = [
            what
            for given, what in (
                (runtime.image, "an image"),
                (runtime.runtime, "an OCI runtime"),
                (runtime.run_args, "run arguments"),
                (runtime.name_prefix, "a name prefix"),
                (
                    runtime.cpus
                    or runtime.memory
                    or runtime.gpus
                    or runtime.gpu_memory,
                    "what it may hand out",
                ),
                (runtime.max_containers, "a container limit"),
            )
            if given
        ]
        if starting:
            raise ValueError(
                f"{name}: a runtime working in the running container "
                f"{runtime.container} starts none, so it cannot say "
                f"{' or '.join(starting)}"
            )


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
      name_prefix: What the name of a service it creates begins with, before the role's
        name and 8 hex digits; "" for `humanize-<name>`.
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
      harness: Where the harness of an agent working on it runs, and nowhere else: see
        :func:`affine`.
      dial_back: The address its nodes reach this machine at, for tasks that dial back to it
        rather than being reached through their node's daemon -- which `nodes` is then not
        asked for; "" for reaching them through it.
    """

    backend: ClassVar[str] = SWARM

    name: str
    endpoint: str = "local"
    tls_dir: str = ""
    image: str = ""
    run_args: tuple[str, ...] = ()
    name_prefix: str = ""
    cpus: float = 0.0
    memory: int = 0
    gpu_resource: str = ""
    constraints: tuple[str, ...] = ()
    max_tasks: int = 0
    nodes: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    harness: str = ENV
    dial_back: str = ""

    def __post_init__(self) -> None:
        _named(self.name)
        _harness(self)
        _endpoint(self.endpoint)
        if self.tls_dir and not self.endpoint.startswith("tcp://"):
            raise ValueError(f"{self.name}: TLS certificates require a tcp:// endpoint")
        _text(self.tls_dir, "the TLS directory")
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: invalid image {self.image!r}")
        if self.dial_back and not re.fullmatch(r"[\w.-]+", self.dial_back, re.ASCII):
            raise ValueError(
                f"{self.name}: invalid dial-back address {self.dial_back!r}: expected a "
                "host name or an IPv4 address"
            )
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: argument {said!r} cannot contain newlines"
                )
        _prefixed(self.name, self.name_prefix)
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
        """The file it is kept in."""
        return settings.where()

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
      harness: Where the harness of an agent working on it runs, and nowhere else: see
        :func:`affine`.
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
    harness: str = ENV

    def __post_init__(self) -> None:
        _named(self.name)
        _harness(self)
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
        """The file it is kept in."""
        return settings.where()

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": APPLE_CONTAINER, **_fields(self)}


#: How long a Slurm job may run, as `--time` takes it: minutes, `MM:SS`, `HH:MM:SS`, or days
#: and a part of one, `D-HH[:MM[:SS]]`; or no limit beyond the partition's.
_TIME = re.compile(
    r"(\d+(:\d{1,2}){0,2}|\d+-\d{1,2}(:\d{1,2}){0,2}|UNLIMITED|INFINITE)\Z"
)

#: A partition, an account or a quality of service: one word Slurm takes as a name.
_SLURM_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*\Z")


@dataclass(frozen=True, slots=True, kw_only=True)
class SlurmRuntime:
    """The Slurm cluster this machine submits to, and how a job of humanize's is asked for.

    Every environment on it is a job of its own, submitted with `sbatch` from here and held
    while the environment is, which the cluster places on whichever node has what the role
    asks for -- and which is then reached by `srun` as a step of that job. There is no daemon
    to name: the cluster is the one this machine's `sbatch` submits to.

    Attributes:
      name: What it is called, which is what an environment on it names.
      partition: The partition a job is submitted to, or "" for the cluster's default.
      account: The account a job is charged to, or "" for the user's default.
      qos: Its quality of service, or "" for the default.
      time: How long a job may run, as `--time` takes it, or "" for the partition's default.
      constraint: The node features a job needs, as `--constraint` takes them, or "".
      python: A Python of at least 3.12 on its nodes, absolute or under `~/`, for a cluster
        whose nodes have none; "" for whatever they have.
      via: How a job's node is reached once it runs: `srun`, a step of the job per
        connection, which every cluster allows; or `tcp`, a connection apiece to the serving
        half the job itself runs, which needs this machine to reach its nodes' ports and
        holds none of the ports `srun` may have here, which a cluster may give it few of.
      run_args: What else `sbatch` is told.
      cpus: How many CPUs its jobs may hold all told, or 0 for as many as the cluster gives.
      memory: How many bytes of memory, likewise.
      max_jobs: How many jobs it may have at once, waiting or running, or 0 for no limit.
      max_wait: How many seconds a job may wait for a node before the environment is given
        up on, or 0 for as long as it waits.
      workdir: Where an `-e` naming it with no workdir works -- a directory every node a job
        may land on has, at the same path.
      fallback: The runtimes an environment an `-e` puts here moves to, in order, where this
        one cannot hold it -- each `<backend>:<name>`.
      made: How it was made, which is :data:`TYPED`.
      harness: Where the harness of an agent working on it runs, and nowhere else: see
        :func:`affine`.
    """

    backend: ClassVar[str] = SLURM

    name: str
    partition: str = ""
    account: str = ""
    qos: str = ""
    time: str = ""
    constraint: str = ""
    python: str = ""
    via: str = "srun"
    run_args: tuple[str, ...] = ()
    cpus: float = 0.0
    memory: int = 0
    max_jobs: int = 0
    max_wait: int = 0
    workdir: str = ""
    fallback: tuple[str, ...] = ()
    made: str = TYPED
    harness: str = ENV

    def __post_init__(self) -> None:
        _named(self.name)
        _harness(self)
        for value, what in (
            (self.partition, "partition"),
            (self.account, "account"),
            (self.qos, "quality of service"),
        ):
            if value and not _SLURM_NAME.match(value):
                raise ValueError(f"{self.name}: invalid {what} {value!r}")
        if self.time and not _TIME.match(self.time):
            raise ValueError(
                f"{self.name}: invalid time {self.time!r}: expected minutes, MM:SS, "
                "HH:MM:SS or D-HH[:MM[:SS]]"
            )
        if self.constraint and (
            self.constraint.startswith("-") or not re.fullmatch(r"\S+", self.constraint)
        ):
            raise ValueError(f"{self.name}: invalid constraint {self.constraint!r}")
        if self.via not in ("srun", "tcp"):
            raise ValueError(f"{self.name}: via must be srun or tcp, not {self.via!r}")
        _text(self.python, "the Python")
        if self.python and not self.python.startswith(("/", "~/")):
            raise ValueError(
                f"{self.name}: the Python {self.python!r} must be absolute or under ~/"
            )
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: argument {said!r} cannot contain newlines"
                )
        for amount, what in (
            (self.cpus, "CPUs"),
            (self.memory, "memory"),
            (self.max_jobs, "jobs"),
            (self.max_wait, "the wait"),
        ):
            if amount < 0:
                raise ValueError(f"{self.name}: {what} cannot be negative: {amount}")
        _workdir(self.workdir)
        _falls_back(SLURM, self.name, self.fallback)
        if self.made != TYPED:
            raise ValueError(
                f"{self.name}: made must be {TYPED} for a Slurm cluster, not {self.made!r}"
            )

    @property
    def at(self) -> Path:
        """The file it is kept in."""
        return settings.where()

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": SLURM, **_fields(self)}


#: One runtime, of whichever backend.
type Runtime = (
    SSHRuntime | DockerRuntime | SwarmRuntime | AppleContainerRuntime | SlurmRuntime
)


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


def saved(backend: str, name: str) -> bool:
    """Whether a runtime of a backend is written down under a name, whether or not it reads.

    Args:
      backend: :data:`SSH`, :data:`DOCKER`, :data:`SWARM`, :data:`APPLE_CONTAINER` or
        :data:`SLURM`.
      name: What the runtime is called.

    Raises:
      ValueError: If the backend is not one of them, or the name is not one a runtime may
        have -- which is what asks it of a name before it is made.
    """
    if backend not in BACKENDS:
        raise ValueError(f"{backend!r} is not a runtime backend: {', '.join(BACKENDS)}")
    return _named(name) in _of(settings.read(), backend)


def _of(held: dict[str, Any], backend: str) -> dict[str, Any]:
    """The runtimes of one backend in one reading of the settings, by name."""
    kept = held.get(_HELD)
    found = (
        cast("dict[str, Any]", kept).get(backend) if isinstance(kept, dict) else None
    )
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}


def new(backend: str, name: str, **fields: Any) -> Runtime:
    """One runtime, checked, and written nowhere.

    Args:
      backend: :data:`SSH`, :data:`DOCKER`, :data:`SWARM`, :data:`APPLE_CONTAINER` or
        :data:`SLURM`.
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
        SLURM: SlurmRuntime,
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
      backend: :data:`SSH`, :data:`DOCKER`, :data:`SWARM`, :data:`APPLE_CONTAINER`,
        :data:`SLURM`, or ""
        for every one.

    Returns:
      One apiece, by backend and then by name. An entry holding nothing readable, or under
      a name no runtime could be made under, is not one and is left out.
    """
    kept = settings.read()
    held: list[Runtime] = []
    for kind in BACKENDS:
        if backend and kind != backend:
            continue
        held.extend(
            one
            for named, said in sorted(
                ((str(each), said) for each, said in _of(kept, kind).items()),
                key=lambda one: one[0],
            )
            if _NAMED.match(named) and (one := _read(kind, named, said)) is not None
        )
    return held


def find(backend: str, name: str) -> Runtime | None:
    """The runtime of a backend called this, or None -- for a name none could have too."""
    if backend not in BACKENDS or not _NAMED.match(name):
        return None
    return _read(backend, name, _of(settings.read(), backend).get(name))


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
    takes in brackets now: `ssh@[gpu]/x`. `docker@local/x`, `swarm@local/x`,
    `apple-container@local/x` and `slurm@local/x` are docker's default here, the swarm this
    machine manages, this Mac's Apple containers and the cluster this machine submits to,
    `docker/x`, `swarm/x`, `apple-container/x` and `slurm/x`, unless a runtime of theirs is
    saved as `local`, which was taken first. `local@/x` is `local/x`.
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
        if saved(backend, provider):
            return spec
    except ValueError:
        pass  # a name no runtime may have, which a destination like `me@box` is
    if backend == SSH:
        return f"{backend}@[{provider}]{at}"
    return f"{backend}{at}" if provider == "local" else spec


def _read(backend: str, name: str, said: object) -> Runtime | None:
    """One runtime read back, or None where nothing readable is there.

    The backend and the name are where it is kept, whatever the entry says: the place is the
    answer, and the entry only describes it.
    """
    if not isinstance(said, dict):
        return None
    fields = {
        str(key): value
        for key, value in cast("dict[Any, Any]", said).items()
        if key not in ("backend", "name")
    }
    # An earlier humanize wrote an ordered `affinity` instead, tried until one had room:
    # read as its first entry, which was where a harness went whenever it could.
    if "affinity" in fields:
        was = fields.pop("affinity")
        if not isinstance(was, list):
            return None
        for first in cast("list[object]", was)[:1]:
            fields.setdefault("harness", ENV if first == "self" else first)
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
    elif isinstance(runtime, DockerRuntime | SwarmRuntime):
        _here(runtime.tls_dir, "the TLS directory")
    saved(runtime.backend, runtime.name)  # which refuses a name no runtime may have
    entry = {
        key: value
        for key, value in runtime.held().items()
        if key not in ("backend", "name")
    }

    def change(held: dict[str, Any]) -> None:
        _making(_making(held, _HELD), runtime.backend)[runtime.name] = entry

    settings.changes(change)
    return runtime


def remove(backend: str, name: str) -> bool:
    """Takes a runtime away.

    Returns:
      Whether there was one to take away.

    Raises:
      ValueError: If the backend or the name is not one there could be.
    """
    if not saved(backend, name):
        return False
    found: list[bool] = []

    def change(held: dict[str, Any]) -> None:
        kept = _of(held, backend)
        found.append(name in kept)
        kept.pop(name, None)

    settings.changes(change)
    return any(found)


def _making(held: dict[str, Any], key: str) -> dict[str, Any]:
    """One mapping in another, made where it is not there or is not a mapping."""
    if not isinstance(held.get(key), dict):
        held[key] = {}
    return cast("dict[str, Any]", held[key])


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
                harness=already.harness if already is not None else ENV,
            )
        except ValueError:
            if names is not None:
                raise
            continue  # a host ssh reads and a runtime cannot hold, left where it is
        making.append(runtime)
    return [cast("SSHRuntime", write(runtime)) for runtime in making]
