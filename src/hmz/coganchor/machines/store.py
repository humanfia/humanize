"""The machines a flow's environments may be put on, written down under names.

An environment provider is one machine an environment can be put on, named by what somebody
called it rather than by how it is reached: an ssh host with the login, port, key and jump host
it takes, or a docker daemon with the resources it may hand out. One directory per provider, under
`~/.humanize/env-providers/<backend>/<name>/`, holding `provider.json`.

Nothing here reaches a machine. What one is when it is asked is
:mod:`hmz.runtime.doing.environments`'s, and reading the user's ssh config is
:mod:`hmz.coganchor.machines.sshconfig`'s; this is only the answer to "which ones are there, and
what is in each".
"""

from __future__ import annotations

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
    "BACKENDS",
    "DOCKER",
    "IMPORTED",
    "SSH",
    "TYPED",
    "DockerProvider",
    "EnvProvider",
    "SSHProvider",
    "add",
    "daemon_of",
    "find",
    "imports",
    "new",
    "providers",
    "remove",
    "under",
    "where",
    "write",
]

#: The backends a provider may be for, by the name `-e` gives each.
SSH = "ssh"
DOCKER = "docker"
BACKENDS = (SSH, DOCKER)

#: How a provider was made: typed in field by field, or read off an ssh config.
TYPED = "typed"
IMPORTED = "imported"

#: What a provider may be called: one path component, holding nothing a shell or a filesystem
#: reads as something else, which cannot climb out of the directory it names.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: What the file a provider is written down in is called.
_HELD = "provider.json"

#: A host, a login or an ssh config alias: a word `ssh` takes as one, never read as an option.
_WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._%+-]*\Z")

#: A jump host, which may be several, as `ProxyJump` takes them.
_JUMP = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._%+@:,\[\]-]*\Z")

#: An ssh_config keyword, as `-o` takes one.
_KEYWORD = re.compile(r"[A-Za-z][A-Za-z0-9]*\Z")

#: The options an ssh provider has a field for, which are set there rather than as options.
_FIELDS = {
    "hostname": "host",
    "user": "user",
    "port": "port",
    "identityfile": "identity_file",
    "proxyjump": "proxy_jump",
}

#: The largest port there is.
_PORT_MAX = 65535


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
    would crash whatever reads the provider; that is a value it cannot take instead.
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


def _named(name: str) -> str:
    if not _NAMED.match(name):
        raise ValueError(
            f"invalid environment provider name {name!r}: must start with a "
            "letter or digit and contain only letters, digits, dots, dashes, "
            "and underscores"
        )
    return name


@dataclass(frozen=True, slots=True, kw_only=True)
class SSHProvider:
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
      made: How it was made: :data:`TYPED` or :data:`IMPORTED`.
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
    made: str = TYPED

    def __post_init__(self) -> None:
        _named(self.name)
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
class DockerProvider:
    """A docker daemon a container may be started on, and what it may hand out.

    Attributes:
      name: What it is called, which is what an environment on it names.
      endpoint: Where the daemon is: `local` for whatever `docker` here reaches,
        `unix:///path.sock`, `tcp://host:port`, `ssh://[user@]host[:port]`,
        `ssh:<name>` for the stored ssh provider of that name, or `context:<name>` for a
        docker context.
      tls_dir: For `tcp://`, the directory holding `ca.pem`, `cert.pem` and `key.pem`.
      image: What a container is started from where the flow says nothing.
      runtime: The container runtime to start one under, e.g. `nvidia`, or "" for the
        daemon's default.
      run_args: What else `docker run` is told.
      cpus: How many CPUs it may hand out, or 0 for as many as it has.
      memory: How many bytes of memory, or 0 for as many as it has.
      gpus: The GPUs it may hand out, by device id -- `("0", "1")` -- or none.
      gpu_memory: How many bytes each of those GPUs has, or 0 for unsaid.
      max_containers: How many containers it may run at once, or 0 for no limit.
      workdir: Where an `-e` naming it with no workdir works.
      made: How it was made, which is :data:`TYPED`.
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
    made: str = TYPED

    def __post_init__(self) -> None:
        _named(self.name)
        _endpoint(self.endpoint)
        if self.tls_dir and not self.endpoint.startswith("tcp://"):
            raise ValueError(f"{self.name}: TLS certificates require a tcp:// endpoint")
        _text(self.tls_dir, "the TLS directory")
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: invalid image {self.image!r}")
        if self.runtime and not _WORD.match(self.runtime):
            raise ValueError(f"{self.name}: invalid runtime {self.runtime!r}")
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
          ValueError: For `ssh:<name>` naming no stored ssh provider.
        """
        return daemon_of(self.endpoint, self.tls_dir)

    def held(self) -> dict[str, Any]:
        """It as it is written down."""
        return {"backend": DOCKER, **_fields(self)}


#: One environment provider, of whichever backend.
type EnvProvider = SSHProvider | DockerProvider


def _fields(provider: EnvProvider) -> dict[str, Any]:
    """Every field of one, as JSON holds it."""
    held: dict[str, Any] = {}
    for one in dataclasses.fields(provider):
        value: object = getattr(provider, one.name)
        if isinstance(value, tuple):
            value = [str(each) for each in cast("tuple[object, ...]", value)]
        elif one.name == "options":
            value = dict(cast("Mapping[str, str]", value))
        held[one.name] = value
    return held


# ------------------------------------------------------------------------ docker endpoints


def _endpoint(endpoint: str) -> str:
    """An endpoint as a provider spells it, checked: one `Endpoint` reads, or `ssh:<name>`.

    Raises:
      ValueError: For one that is neither.
    """
    from hmz.coganchor.transport import Endpoint

    if endpoint.startswith("ssh:") and not endpoint.startswith("ssh://"):
        if _NAMED.match(endpoint[len("ssh:") :]):
            return endpoint
    elif endpoint.startswith("ssh://"):
        # A word ssh reads as a login or a host, never as an option, and nothing after it:
        # what else a daemon's host needs is said by an ssh provider, `ssh:<name>`.
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
    """The daemon an endpoint names, as a provider spells it, for `docker` to be pointed at.

    What a provider adds to :class:`~hmz.coganchor.transport.Endpoint`, which is the one place
    an endpoint becomes a command line: its certificates beside it rather than in it, and
    `ssh:<name>` for the stored ssh provider a daemon's host is reached as -- dialled with
    everything that provider says.

    Args:
      endpoint: As :attr:`DockerProvider.endpoint` spells it.
      tls_dir: For `tcp://`, the directory of its certificates, or "" for none.

    Returns:
      The daemon.

    Raises:
      ValueError: For an endpoint that is none of them, `ssh:<name>` naming no stored
        ssh provider, or certificates under a home there is none of.
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
    found = cast("SSHProvider", found)
    port = f":{found.port}" if found.port else ""
    return Endpoint(host=f"ssh://{found.login()}{port}", options=found.settings())


# ---------------------------------------------------------------------------- the store


def under() -> Path:
    """Where every environment provider is kept, whether or not anything is."""
    return home() / "env-providers"


def where(backend: str, name: str) -> Path:
    """The directory one provider is kept in.

    Args:
      backend: :data:`SSH` or :data:`DOCKER`.
      name: What the provider is called.

    Returns:
      The path, whether or not anything is there yet.

    Raises:
      ValueError: If the backend is not one of them, or the name is not one a provider may
        have.
    """
    if backend not in BACKENDS:
        raise ValueError(
            f"{backend!r} is not an environment backend: {', '.join(BACKENDS)}"
        )
    return under() / backend / _named(name)


def new(backend: str, name: str, **fields: Any) -> EnvProvider:
    """One provider, checked, and written nowhere.

    Args:
      backend: :data:`SSH` or :data:`DOCKER`.
      name: What it is called.
      **fields: The rest of it, by field -- as :meth:`SSHProvider.held` writes them, lists and
        numbers as JSON has them.

    Returns:
      It.

    Raises:
      ValueError: If it is not a provider of that backend: a field it has not got, or a
        value it cannot take.
    """
    if backend not in BACKENDS:
        raise ValueError(
            f"{backend!r} is not an environment backend: {', '.join(BACKENDS)}"
        )
    kind: type[EnvProvider] = SSHProvider if backend == SSH else DockerProvider
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
    if key == "options":
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


def providers(backend: str = "") -> list[EnvProvider]:
    """Every provider there is, or every one of a backend.

    Args:
      backend: :data:`SSH`, :data:`DOCKER`, or "" for both.

    Returns:
      One apiece, by backend and then by name. A directory holding nothing readable, or
      under a name no provider could be made under, is not one and is left out.
    """
    held: list[EnvProvider] = []
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


def find(backend: str, name: str) -> EnvProvider | None:
    """The provider of a backend called this, or None -- for a name none could have too."""
    if backend not in BACKENDS or not _NAMED.match(name):
        return None
    return _read(backend, name)


def _read(backend: str, name: str) -> EnvProvider | None:
    """One provider read back, or None where nothing readable is there.

    The backend and the name are where it is kept, whatever the file says: the place is the
    answer, and the file only describes it.
    """
    try:
        said = json.loads(
            (under() / backend / name / _HELD).read_text(encoding="utf-8")
        )
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


def add(provider: EnvProvider) -> EnvProvider:
    """Writes a new provider down.

    Raises:
      ValueError: If there is one of that backend under that name already, or it names a
        path under a home there is none of.
      OSError: If it cannot be written.
    """
    if find(provider.backend, provider.name) is not None:
        raise ValueError(f"{provider.backend} host {provider.name!r} already exists")
    return write(provider)


def write(provider: EnvProvider) -> EnvProvider:
    """Writes a provider down, whole, over whatever was under its name.

    Returns:
      It, as it is now written down.

    Raises:
      ValueError: If it names a config file or certificates under a home there is none of,
        which would be a provider nothing could reach. Refused here rather than where it is
        made, so that one written down while its home was there is still listed -- and
        checked, saying why -- once it has gone.
      OSError: If it cannot be written.
    """
    if isinstance(provider, SSHProvider):
        _here(provider.config, "the config file")
    else:
        _here(provider.tls_dir, "the TLS directory")
    at = where(provider.backend, provider.name)
    _kept(at)
    _writes(at / _HELD, json.dumps(provider.held(), indent=2) + "\n")
    return provider


def remove(backend: str, name: str) -> bool:
    """Takes a provider away.

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
) -> list[SSHProvider]:
    """Writes an ssh provider down for each host an ssh config names.

    Each is called after its `Host`, with anything no provider name may hold made a dash,
    and holds the alias rather than what it resolves to: `ssh` goes on reading the config
    for it, so the config goes on being what it says.

    Args:
      config: The config file, or None for the user's own.
      names: The hosts to import, by their `Host`, or None for every one.
      update: Whether to write over a provider of that name an import made -- keeping the
        workdir it was given -- rather than leave it be. One typed in is never written over.

    Returns:
      The providers written, in the order the config names them.

    Raises:
      ValueError: If `names` names a host the config does not, or one that cannot be a
        provider: under no name, under the name of another host named, or -- to be updated --
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
    making: list[SSHProvider] = []
    seen: dict[str, str] = {}
    for alias in wanted:
        name = re.sub(r"[^A-Za-z0-9._-]", "-", alias).lstrip("._-")
        already = find(SSH, name) if name else None
        # A provider somebody typed in is theirs, and an import does not write over it; nor
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
            provider = SSHProvider(
                name=name,
                alias=alias,
                config=str(Path(_here(str(config), "the config")).resolve())
                if own and config
                else "",
                workdir=already.workdir if already is not None else "",
                made=IMPORTED,
            )
        except ValueError:
            if names is not None:
                raise
            continue  # a host ssh reads and a provider cannot hold, left where it is
        making.append(provider)
    return [cast("SSHProvider", write(provider)) for provider in making]
