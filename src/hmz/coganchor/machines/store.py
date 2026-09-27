"""The machines a flow's environments may be put on, written down under names.

An environment provider is one machine an environment can be put on, named by what somebody
called it rather than by how it is reached: an ssh host with the login, port, key and jump host
it takes, or a docker daemon with the resources it may hand out. One directory per provider, under
`~/.humanize/env-providers/<backend>/<name>/`, holding `provider.json` -- and, for an ssh host a
docker daemon is reached through, the `ssh` that daemon's own ssh is to run.

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
import shlex
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz import home

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

__all__ = [
    "BACKENDS",
    "DOCKER",
    "IMPORTED",
    "SSH",
    "TYPED",
    "DockerDaemon",
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
        raise ValueError(f"{what} {value!r} is more than one line, or holds a quote")
    return value


def _workdir(value: str) -> str:
    """A default workdir: absolute, or under the login's home, or none at all."""
    _text(value, "the workdir")
    if value and value != "~" and not value.startswith(("/", "~/")):
        raise ValueError(f"the workdir {value!r} is neither absolute nor under ~/")
    return value


def _named(name: str) -> str:
    if not _NAMED.match(name):
        raise ValueError(
            f"{name!r} is not an environment provider name: letters, digits, dot, dash "
            "and underscore, starting with a letter or a digit"
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
            raise ValueError(f"{self.name}: an ssh provider needs a host or an alias")
        for value, what in (
            (self.host, "host"),
            (self.alias, "alias"),
            (self.user, "user"),
        ):
            if value and not _WORD.match(value):
                raise ValueError(f"{self.name}: {value!r} is not an ssh {what}")
        if not 0 <= self.port <= _PORT_MAX:
            raise ValueError(f"{self.name}: {self.port} is not a port")
        if self.proxy_jump and not _JUMP.match(self.proxy_jump):
            raise ValueError(f"{self.name}: {self.proxy_jump!r} is not a jump host")
        _text(self.identity_file, "the identity file")
        _text(self.config, "the config file")
        _workdir(self.workdir)
        if self.made not in (TYPED, IMPORTED):
            raise ValueError(
                f"{self.name}: made {self.made!r}, not {TYPED} or {IMPORTED}"
            )
        for key, value in self.options.items():
            if not _KEYWORD.match(key) or key == "F":
                raise ValueError(f"{self.name}: {key!r} is not an ssh option")
            if key.lower() in _FIELDS:
                raise ValueError(
                    f"{self.name}: {key} is said with {_FIELDS[key.lower()]}, not as an option"
                )
            if not value:
                raise ValueError(f"{self.name}: the option {key} says nothing")
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
        """
        said: list[tuple[str, str]] = []
        if self.config:
            said.append(("F", str(Path(self.config).expanduser())))
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
        kind, _ = _endpoint(self.endpoint)
        if self.tls_dir and kind != "tcp":
            raise ValueError(f"{self.name}: TLS certificates are for a tcp:// endpoint")
        _text(self.tls_dir, "the TLS directory")
        if self.image and not re.fullmatch(r"[^\s]+", self.image):
            raise ValueError(f"{self.name}: {self.image!r} is not an image")
        if self.runtime and not _WORD.match(self.runtime):
            raise ValueError(f"{self.name}: {self.runtime!r} is not a runtime")
        for said in self.run_args:
            if set(said) & set("\n\r\0"):
                raise ValueError(
                    f"{self.name}: the argument {said!r} is more than one line"
                )
        for gpu in self.gpus:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", gpu):
                raise ValueError(f"{self.name}: {gpu!r} is not a GPU id")
        if len(set(self.gpus)) != len(self.gpus):
            raise ValueError(f"{self.name}: a GPU is named twice")
        for amount, what in (
            (self.cpus, "CPUs"),
            (self.memory, "memory"),
            (self.gpu_memory, "GPU memory"),
            (self.max_containers, "containers"),
        ):
            if amount < 0:
                raise ValueError(f"{self.name}: {amount} is not an amount of {what}")
        _workdir(self.workdir)
        if self.made != TYPED:
            raise ValueError(f"{self.name}: a docker provider is only ever {TYPED}")

    @property
    def at(self) -> Path:
        """The directory it is kept in."""
        return where(DOCKER, self.name)

    def daemon(self) -> DockerDaemon:
        """How the `docker` command line reaches this one's daemon.

        Raises:
          ValueError: For `ssh:<name>` naming no stored ssh provider.
          OSError: If what that provider's ssh is to run cannot be written.
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


@dataclass(frozen=True, slots=True)
class DockerDaemon:
    """How the `docker` command line is pointed at one daemon.

    Attributes:
      endpoint: The endpoint, as a provider spells it.
      args: What `docker` is told before the command: `--host ...`, `--context ...`, and the
        TLS flags for a tcp:// daemon.
      env: What it has to run with on top of this process's environment, which is only ever
        `PATH`, with the `ssh` of a stored ssh provider in front.
    """

    endpoint: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)

    def command(self, argv: Sequence[str]) -> list[str]:
        """The command that runs `docker <argv>` against this daemon, whole.

        Args:
          argv: The docker command and its arguments, e.g. `["info"]`.

        Returns:
          The argv to spawn, as it is: what it has to run with is on it, through `env`.
        """
        told = ["env", *(f"{key}={value}" for key, value in self.env.items())]
        return [*(told if self.env else ()), "docker", *self.args, *argv]


def _endpoint(endpoint: str) -> tuple[str, str]:
    """An endpoint read: which kind, and what follows the kind.

    Raises:
      ValueError: For one that is none of them.
    """
    if endpoint == "local":
        return "local", ""
    if endpoint.startswith("unix://") and endpoint[len("unix://") :].startswith("/"):
        return "unix", endpoint[len("unix://") :]
    if endpoint.startswith("tcp://"):
        host, _, port = endpoint[len("tcp://") :].rpartition(":")
        if host and port.isdigit() and 0 < int(port) <= _PORT_MAX:
            return "tcp", endpoint[len("tcp://") :]
    if endpoint.startswith("ssh://"):
        login, _, where_ = endpoint[len("ssh://") :].rpartition("@")
        host, _, port = where_.partition(":")
        if (
            _WORD.match(host)
            and (not login or _WORD.match(login))
            and (not port or (port.isdigit() and 0 < int(port) <= _PORT_MAX))
        ):
            return "ssh", endpoint[len("ssh://") :]
    if endpoint.startswith("ssh:") and _NAMED.match(endpoint[len("ssh:") :]):
        return "provider", endpoint[len("ssh:") :]
    if endpoint.startswith("context:") and _NAMED.match(endpoint[len("context:") :]):
        return "context", endpoint[len("context:") :]
    raise ValueError(
        f"{endpoint!r} is not a docker endpoint: local, unix:///PATH, tcp://HOST:PORT, "
        "ssh://[USER@]HOST[:PORT], ssh:<ssh provider> or context:<docker context>"
    )


def daemon_of(endpoint: str, tls_dir: str = "") -> DockerDaemon:
    """How the `docker` command line reaches the daemon an endpoint names.

    The one place an endpoint becomes a command line, for whatever starts a container on one
    and whatever asks one what it has.

    Args:
      endpoint: As :attr:`DockerProvider.endpoint` spells it.
      tls_dir: For `tcp://`, the directory of its certificates, or "" for none.

    Returns:
      The daemon, as `docker` is to be told it.

    Raises:
      ValueError: For an endpoint that is none of them, or `ssh:<name>` naming no stored
        ssh provider.
      OSError: If the `ssh` that provider's options need cannot be written.
    """
    kind, rest = _endpoint(endpoint)
    if kind == "local":
        return DockerDaemon(endpoint)
    if kind == "context":
        return DockerDaemon(endpoint, ("--context", rest))
    if kind == "tcp" and tls_dir:
        certs = Path(tls_dir).expanduser()
        return DockerDaemon(
            endpoint,
            (
                "--host",
                endpoint,
                "--tlsverify",
                "--tlscacert",
                str(certs / "ca.pem"),
                "--tlscert",
                str(certs / "cert.pem"),
                "--tlskey",
                str(certs / "key.pem"),
            ),
        )
    if kind != "provider":
        return DockerDaemon(endpoint, ("--host", endpoint))
    found = find(SSH, rest)
    if found is None:
        raise ValueError(f"{endpoint}: there is no ssh provider called {rest!r}")
    found = cast("SSHProvider", found)
    url = f"ssh://{found.login()}" + (f":{found.port}" if found.port else "")
    settings = found.settings()
    if not settings:
        return DockerDaemon(endpoint, ("--host", url))
    # docker dials an ssh host with the `ssh` on its PATH and tells it only the login, the
    # port and the host. The rest of what the provider says goes in an `ssh` of its own, put
    # in front of the real one for the `docker` that is to dial it.
    at = _shim(found, settings)
    return DockerDaemon(
        endpoint,
        ("--host", url),
        {"PATH": f"{at}{os.pathsep}{os.environ.get('PATH', os.defpath)}"},
    )


def _shim(provider: SSHProvider, settings: Sequence[tuple[str, str]]) -> Path:
    """Writes the `ssh` a docker daemon behind this provider is dialled through.

    Returns:
      The directory it is in, which goes in front of `PATH`; it takes itself off again
      before running the real one.
    """
    from hmz.coganchor.transport import ssh_flags

    at = provider.at / "bin"
    _kept(at)
    flags = " ".join(shlex.quote(flag) for flag in ssh_flags(settings))
    _writes(
        at / "ssh",
        "#!/bin/sh\n"
        f"# The ssh docker dials {provider.name} through, told what it says.\n"
        f"PATH=${{PATH#{shlex.quote(str(at) + os.pathsep)}}}\n"
        f'exec ssh {flags} "$@"\n',
        mode=0o700,
    )
    return at


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
            raise ValueError(f"{name}: a {backend} provider has no {key!r}")
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
      ValueError: If there is one of that backend under that name already.
      OSError: If it cannot be written.
    """
    if find(provider.backend, provider.name) is not None:
        raise ValueError(
            f"{provider.backend} already has a provider called {provider.name!r}"
        )
    return write(provider)


def write(provider: EnvProvider) -> EnvProvider:
    """Writes a provider down, whole, over whatever was under its name.

    Returns:
      It, as it is now written down.

    Raises:
      OSError: If it cannot be written.
    """
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
    handle, beside = tempfile.mkstemp(
        dir=at.parent, prefix=f".{at.name}.", suffix=".new"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(said)
        Path(beside).chmod(mode)
        Path(beside).replace(at)
    except OSError:
        Path(beside).unlink(missing_ok=True)
        raise


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
        raise ValueError(f"the ssh config names no host {', '.join(missing)}")
    own = config is not None and Path(config).expanduser().resolve() != (
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
                config=str(Path(config).expanduser().resolve())
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
