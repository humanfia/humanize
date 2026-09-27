"""A container of one image, holding the workspace at the path it already has on its host.

The project directory is mounted rather than copied, and the container runs as whoever owns
it, so what a turn writes there is that user's file in that user's directory and survives the
container it was written from. Everything else -- the tools, the interpreters, the libraries a
command reaches for -- is the image's, which is what the isolation is.

The daemon may be this machine's or another's: an :class:`~hmz.coganchor.transport.Endpoint`
names it, and every command for the container goes to that daemon and no other. On a daemon
elsewhere the workspace is a path on *its* host, so it is asked for there rather than looked
for here. What the container may take of that host -- CPUs, memory, GPUs -- is said in the
setting and written on the container as labels, so that whoever shares out a daemon can read
back what is already taken with :func:`allocations`.

Driven through the `docker` command rather than a client library, because that is what a turn
reaches the container through: coganchor's `docker://` target runs its own half over
`docker exec`, and one machine is best spoken to in one voice.
"""

from __future__ import annotations

import contextlib
import csv
import errno
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from hmz.coganchor import AnchorConfig
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE
from hmz.coganchor.transport import Endpoint, Road, Target, python_command

from .base import MachineBase, MachineConfig

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: What the container does while the turns come and go: nothing, in the interpreter coganchor's
#: target half needs, looked for the way that half looks for it -- the same machine and the
#: same Python, so an image keeping one off `PATH` is served rather than refused. An image
#: holding none at all is a container that stops as it starts, and so is a flow that fails
#: where it is set up rather than a turn later.
_IDLE = tuple(python_command(["-c", "import time; time.sleep(2**31)"]))

#: Asking a container whose the directory it was given is, in the same interpreter.
_OWNER = "import os, sys; held = os.stat(sys.argv[1]); print(held.st_uid, held.st_gid)"

#: Marks a container as one of ours, and whose, for whoever has to clean up after a flow that
#: was killed before it could. Named for the project rather than for this layer, since it is
#: read by whoever runs `docker ps`, to whom the layers are not a thing.
_LABEL = "humanize"

#: What a container was given of its daemon's host, written on it beside that: CPUs as a
#: number, memory in bytes, and GPUs as their ids joined by commas or `all`.
CPUS = "humanize.cpus"
MEMORY = "humanize.memory"
GPUS = "humanize.gpus"

#: The kind of device an NVIDIA GPU is listed as, where the daemon lists them.
CDI = _CDI = "nvidia.com/gpu"

#: What docker takes as a container's name.
_NAMED = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+")

#: And what :data:`_OWNER` answers with.
_OWNED = re.compile(r"(\d+) (\d+)\s*\Z")


@dataclass(frozen=True, kw_only=True)
class DockerConfig(MachineConfig):
    """What the container is run from, and on which daemon.

    Attributes:
      image: The image to run, which needs `/bin/sh` and a Python of at least 3.12 for
        coganchor's target half, and whatever else the agent is expected to reach for.
      workspace: The project directory to give the container, as its daemon's host names it,
        defaulting to this directory. It is the directory itself that goes there, not a copy
        of it, so the work outlives the container.
      endpoint: The daemon to run it on, as :class:`~hmz.coganchor.transport.Endpoint` reads
        one: `local` for docker's default here, `unix:///PATH`, `tcp://HOST:PORT[?tls=DIR]`,
        `ssh://[USER@]HOST[:PORT]` or `context:NAME`.
      name: What to call the container, or None for a name of its own. A config that names
        its container brings up one at a time: a second agent given it while the first still
        holds the name is refused by docker.
      cpus: How many of the host's CPUs it may use, or None for no limit.
      memory: How many bytes of memory it may use, or None for no limit.
      shm_size: How large its `/dev/shm` is, in bytes, or None for docker's default.
      gpus: The ids of the GPUs it is given, as `nvidia-smi` names them, or `all`. None
        reach it otherwise, even on a daemon whose runtime would hand an image asking for
        them every one it has.
      runtime: The OCI runtime to run it under, or None for the daemon's default.
      network: The network to put it on, or None for the daemon's default.
      run_args: What else `docker run` is told, ahead of the image -- a daemon's own mounts,
        devices or options, as whoever runs it says it is to be run. Said before humanize's
        own resources and GPUs, which a later flag of docker's outranks.
      env: Variables to set in it.
      labels: Labels to put on it beside humanize's own, which are never taken from here:
        what a container holds is read back off those, and they say only what it was given.
    """

    image: str = "python:3.12"
    workspace: str | None = None
    endpoint: str = "local"
    name: str | None = None
    cpus: float | None = None
    memory: int | None = None
    shm_size: int | None = None
    gpus: tuple[str, ...] | Literal["all"] = ()
    runtime: str | None = None
    network: str | None = None
    run_args: tuple[str, ...] = ()
    # Left out of the hash, which the rest of the setting still answers for: a mapping has
    # none, and a frozen setting that could not be hashed is one no set could hold.
    env: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    labels: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)

    def __post_init__(self) -> None:
        """Refuses what docker would refuse, where it is written rather than as it starts.

        Raises:
          ValueError: If the endpoint cannot be read, the name is not one docker takes, a
            limit is not more than nothing, a GPU is not named, or a variable or a label
            has no name.
        """
        Endpoint.parse(self.endpoint)
        if self.name is not None and not _NAMED.fullmatch(self.name):
            raise ValueError(f"unsupported container name {self.name!r}")
        for what, limit in (
            ("cpus", self.cpus),
            ("memory", self.memory),
            ("shm_size", self.shm_size),
        ):
            if limit is not None and limit <= 0:
                raise ValueError(f"{what} must be more than nothing, not {limit!r}")
        # Read as whatever it was handed, so that ids given as numbers are taken and a
        # string that is not `all` is refused rather than read a character at a time.
        gpus = cast("object", self.gpus)
        if gpus != "all":
            if not isinstance(gpus, tuple | list):
                raise ValueError(f"gpus must be ids or 'all', not {gpus!r}")
            ids = tuple(str(one) for one in cast("tuple[object, ...]", gpus))
            if not all(ids) or any("," in one for one in ids):
                raise ValueError(f"unsupported gpus {ids!r}; expected their ids")
            object.__setattr__(self, "gpus", ids)
        for key in (*self.env, *self.labels):
            if not key or "=" in key:
                raise ValueError(f"unsupported name {key!r}; expected one without '='")
        object.__setattr__(self, "run_args", tuple(str(one) for one in self.run_args))
        # Copies, so the caller's own dictionary changing later does not change the setting.
        object.__setattr__(self, "env", dict(self.env))
        object.__setattr__(self, "labels", dict(self.labels))

    @property
    def capabilities(self) -> frozenset[str]:
        """`remote`, `isolated`, `managed` and `linux`.

        `isolated` because the tools a command finds there are the image's rather than this
        machine's, which is the whole of what a container is reached for. `managed` because
        the container is started for the agent and goes down with it -- which is what tells a
        machine anybody here may take down from one nobody here may. And `linux` because a
        container of an image is a Linux userland whatever the daemon happens to be running
        on, which is the one of the four the machine itself can contradict: :meth:`Docker.start`
        asks it, and refuses a container that says otherwise.

        And the road, for the reason an anchored place says it: a container is reached by an
        anchor like any other target, and this is the one place in humanize certain of which
        anchor it will be -- :meth:`Docker.start` builds a supervised one every time.

        The words are :mod:`hmz.coganchor.places`' own. `linux` is the one of the four this
        module names as a literal, since it is a platform rather than a kind of place: which
        platforms have a word at all is settled on the wire, and what is asserted here is that
        a container is one particular one of them.
        """
        return (
            frozenset({ISOLATED, "linux", MANAGED, REMOTE})
            | AnchorConfig().capabilities
        )

    def create(self) -> Docker:
        """Builds the backend, without starting a container yet."""
        return Docker(self)


@dataclass(frozen=True, slots=True)
class Allocation:
    """One of humanize's containers running on a daemon, and what it was given there.

    Attributes:
      name: The container.
      cpus: The CPUs it may use, or None for no limit.
      memory: The bytes of memory it may use, or None for no limit.
      gpus: The GPUs it was given, or `all`.
      labels: Every label it carries, humanize's own among them.
    """

    name: str
    cpus: float | None
    memory: int | None
    gpus: tuple[str, ...] | Literal["all"]
    labels: Mapping[str, str]


def allocations(
    endpoint: str = "local",
    labels: Mapping[str, str] | None = None,
    *,
    seconds: float | None = None,
) -> list[Allocation]:
    """What humanize's running containers on one daemon hold of its host.

    Whoever started them: a daemon is shared out between everybody using it, and a container
    is holding its share whichever user's flow brought it up.

    Args:
      endpoint: The daemon to ask, spelled as :attr:`DockerConfig.endpoint` is.
      labels: Labels a container must also carry to be counted, such as the provider it was
        allocated from.
      seconds: How long each question may take, or None for as long as the daemon does.

    Returns:
      One allocation per container, read off the labels it was started with.

    Raises:
      ValueError: If the endpoint cannot be read.
      OSError: If the daemon cannot be asked, or did not answer in time.
    """
    where = Endpoint.parse(endpoint)
    wanted = [f"label={_LABEL}"]
    wanted += [f"label={key}={value}" for key, value in (labels or {}).items()]
    listed = _asked(
        where.docker(
            "ps",
            "--quiet",
            "--no-trunc",
            *(word for one in wanted for word in ("--filter", one)),
        ),
        seconds,
    )
    if listed.returncode != 0:
        raise OSError(f"could not ask {where} what it runs: {listed.stderr.strip()}")
    held = listed.stdout.split()
    if not held:
        return []
    inspected = _asked(where.docker("inspect", *held), seconds)
    # A container that went between the two questions is one docker names as missing while
    # still answering for the rest; anything else it says it could not do is a daemon that
    # was not asked, which is not the same as one with nothing on it.
    trouble = [
        line
        for line in inspected.stderr.splitlines()
        if line.strip() and "no such" not in line.lower()
    ]
    try:
        if inspected.returncode != 0 and trouble:
            raise ValueError(trouble)  # noqa: TRY301 -- answered with the parse failure below
        found = cast("list[dict[str, Any]]", json.loads(inspected.stdout or "[]"))
    except ValueError as why:
        raise OSError(
            f"could not ask {where} what it runs: {inspected.stderr.strip()}"
        ) from why
    return [_allocation(one) for one in found]


def info(endpoint: str = "local", seconds: float | None = None) -> dict[str, Any]:
    """What a daemon says of itself, as `docker info` says it.

    Args:
      endpoint: The daemon to ask, spelled as :attr:`DockerConfig.endpoint` is.
      seconds: How long it may take, or None for as long as the daemon does.

    Returns:
      Everything it said.

    Raises:
      ValueError: If the endpoint cannot be read.
      OSError: If there is no `docker` here, the daemon could not be asked or did not answer
        in time, or it said it could not answer -- in its own words.
    """
    where = Endpoint.parse(endpoint)
    said = _asked(where.docker("info", "--format", "{{json .}}"), seconds)
    told: object = None
    with contextlib.suppress(ValueError):
        told = json.loads(said.stdout) if said.stdout.strip() else None
    held = cast("dict[str, Any]", told) if isinstance(told, dict) else {}
    errors = [str(one) for one in cast("list[Any]", held.get("ServerErrors") or [])]
    if said.returncode or errors or not held.get("ServerVersion"):
        why = "; ".join(errors) or said.stderr.strip() or f"exit {said.returncode}"
        raise OSError(f"could not ask {where} what it has: {why}")
    return held


def gpus_listed(devices: Sequence[Any], kind: str = "") -> tuple[str, ...]:
    """The GPUs a daemon's CDI devices name, by index where it names them by index.

    A GPU is listed under several names -- its index, its UUID, and again under each vendor
    that registered it -- so the indices are the answer where there are any, and the other
    names, less `all`, where there are not.

    Args:
      devices: `DiscoveredDevices`, as `docker info` says it.
      kind: The one kind of device to read, such as :data:`CDI`, or "" for every GPU.
    """
    names: list[str] = []
    for device in devices:
        said: Mapping[str, Any] = (
            cast("Mapping[str, Any]", device) if isinstance(device, dict) else {}
        )
        listed, _, name = str(said.get("ID") or "").partition("=")
        wanted = listed == kind if kind else listed.endswith("/gpu")
        if wanted and name and name != "all" and name not in names:
            names.append(name)
    indices = sorted((one for one in names if one.isdigit()), key=int)
    return tuple(indices or names)


def _asked(argv: list[str], seconds: float | None) -> subprocess.CompletedProcess[str]:
    """Runs one question for a daemon, with nothing on its stdin, for so long at most.

    Raises:
      OSError: If it could not be run, or did not answer in time.
    """
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise OSError(
            errno.ETIMEDOUT, f"{argv[0]} did not answer within {seconds:g}s"
        ) from error


def _allocation(inspected: Mapping[str, Any]) -> Allocation:
    """What one container holds, as `docker inspect` said it."""
    config = cast("dict[str, Any]", inspected.get("Config") or {})
    said = {
        str(key): str(value)
        for key, value in cast("dict[str, Any]", config.get("Labels") or {}).items()
    }
    gpus = said.get(GPUS, "")
    return Allocation(
        name=str(inspected.get("Name", "")).lstrip("/"),
        cpus=_number(said.get(CPUS), float),
        memory=_number(said.get(MEMORY), int),
        gpus="all" if gpus == "all" else tuple(one for one in gpus.split(",") if one),
        labels=said,
    )


def _number[N: (int, float)](label: str | None, kind: type[N]) -> N | None:
    """A label read as the number it should hold, or None where it holds none.

    Rather than raising: a label is anybody's to write on a container, and one written wrong
    on somebody else's must not stop every reader of the daemon from counting the rest.
    """
    try:
        return kind(label) if label is not None else None
    except ValueError:
        return None


class Docker(MachineBase):
    """One container, and the mirror the agent works in while its turns land there."""

    _config: DockerConfig

    def __init__(self, config: DockerConfig) -> None:
        """Initializes a backend holding no container.

        Args:
          config: The image, the workspace and the daemon the container is started with.
        """
        super().__init__(config)
        self._endpoint = Endpoint.parse(config.endpoint)
        self._mirror: tempfile.TemporaryDirectory[str] | None = None
        self._told: dict[str, Any] | None = None

    def start(self) -> AnchorConfig:
        """Starts the container and asks it what it is holding.

        Returns:
          The anchor that reaches it, which names the workspace by the path it has on the
          daemon's host and the container by a target carrying that daemon.

        Raises:
          FileNotFoundError: If there is no workspace directory to give the container, or no
            `docker` to give it to.
          ValueError: If the workspace on a daemon elsewhere is not an absolute path, which is
            the only kind a path on another machine can be.
          RuntimeError: If the container cannot be started -- an image with no shell in it,
            or none holding a Python new enough, is refused here. What docker said is
            attached. Or if what came up is not the machine these settings promised, which
            names the capability it could not serve.
          OSError: If the container cannot serve the workspace it was mounted, which is a turn
            that would fail on its first file, reported before the first turn instead. An
            image holding no Python the target half can use is refused here too: the idle
            process is what looks for one, so an image without one holds no container to
            serve from by the time this asks.
        """
        config = self._config
        endpoint = self._endpoint
        if shutil.which("docker") is None:
            # Asked here, since a `docker` reached through `env` is one whose absence would
            # otherwise read as a container that would not start.
            raise FileNotFoundError(errno.ENOENT, "no docker command here", "docker")
        if endpoint.here:
            # `abspath` rather than `Path.resolve`: what is mounted is the directory named,
            # and a workspace reached through a symlink is not a request to mount what it
            # points at.
            workspace = os.path.abspath(config.workspace or os.getcwd())  # noqa: PTH100, PTH109
            if not Path(workspace).is_dir():
                raise FileNotFoundError(
                    errno.ENOENT, "no directory to give the container", workspace
                )
        else:
            workspace = posixpath.normpath(config.workspace or os.getcwd())  # noqa: PTH109
            if not workspace.startswith("/"):
                raise ValueError(
                    f"a workspace on {endpoint} is a path on that machine, so it has to be "
                    f"an absolute one, not {workspace!r}"
                )
        # A mirror of its own, never the workspace: coganchor overwrites a mirror with what the
        # target has, and here the target's copy *is* the workspace, mounted rather than
        # mirrored. Nothing of the work lives in the mirror, so it goes with the container,
        # which is named after it so that the two read as one thing wherever they turn up.
        self._mirror = tempfile.TemporaryDirectory(
            prefix="humanize-", ignore_cleanup_errors=True
        )
        name = config.name or Path(self._mirror.name).name
        # Read back rather than written out, so a container on the default names no daemon
        # whichever way that default was spelled.
        target = Target.parse(f"docker://{name}@{endpoint}")
        try:
            gpus, by_name = self._gpus()
            started = subprocess.run(
                endpoint.docker(
                    "run",
                    "--detach",
                    # Where docker writes the id of what it created, which is the one thing
                    # `stop` may remove: a name somebody else's container already had is a
                    # container this never made.
                    "--cidfile",
                    self._made(),
                    "--name",
                    name,
                    *self._labelled(),
                    "--user",
                    self._whose(workspace),
                    "--workdir",
                    workspace,
                    *self._environment(visible=not gpus or by_name),
                    # `--mount` rather than `--volume`, which would make a missing source
                    # into a directory owned by root on a host nobody here can see.
                    "--mount",
                    _bound(workspace),
                    *config.run_args,
                    *self._resources(),
                    *gpus,
                    config.image,
                    *_IDLE,
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            if started.returncode != 0:
                # Raised here rather than below: everything in this block may have a
                # container behind it by now, and the handler is what takes it back down.
                raise RuntimeError(  # noqa: TRY301
                    f"could not start a container of {config.image} on {endpoint}: "
                    f"{started.stderr.strip()}"
                )
            # A container made just now holds no bundle, whatever one of the same name was
            # given before it on this daemon.
            Road.to(target).forget()
            anchor = AnchorConfig(
                target=target.describe(),
                workspace=workspace,
                shadow=str(Path(self._mirror.name) / "shadow"),
            )
            # Raises unless it is the workspace we mounted that it serves, and unless the
            # container is the machine this config promised -- one handshake answering both,
            # since what a target says of itself comes back with the workspace either way.
            self.observe(anchor)
        except BaseException:
            self.stop()
            raise
        return anchor

    def stop(self) -> None:
        """Removes the container and the mirror, leaving the workspace as the turns left it."""
        if self._mirror is None:
            return
        try:
            made = Path(self._made()).read_text().strip()
        except OSError:
            made = ""  # docker never got as far as making one
        if made:
            subprocess.run(
                self._endpoint.docker("rm", "--force", made),
                capture_output=True,
                check=False,
            )
        self._mirror.cleanup()

    def _made(self) -> str:
        """Where docker says which container it made, beside the mirror it is named for."""
        assert self._mirror is not None  # noqa: S101 -- asked only once there is one
        return str(Path(self._mirror.name) / "container")

    def _labelled(self) -> list[str]:
        """The labels: the caller's, then whose it is and what it holds of the host."""
        config = self._config
        # Whose it is, so that sweeping up after a flow that was killed outright cannot
        # reach past this user on a machine several of them share. And none of humanize's
        # own from the caller, even where the setting says nothing of its own under that
        # name: a limit that is only a label is one `allocations` would count as taken.
        said = {
            key: value
            for key, value in config.labels.items()
            if key not in (_LABEL, CPUS, MEMORY, GPUS)
        }
        said[_LABEL] = str(os.getuid())
        if config.cpus is not None:
            said[CPUS] = f"{config.cpus:g}"
        if config.memory is not None:
            said[MEMORY] = str(config.memory)
        if config.gpus:
            said[GPUS] = "all" if config.gpus == "all" else ",".join(config.gpus)
        return [
            word
            for key, value in said.items()
            for word in ("--label", f"{key}={value}")
        ]

    def _environment(self, *, visible: bool) -> list[str]:
        """Its variables: a home, the caller's, and no GPU but those handed it by name.

        Args:
          visible: Whether to say that the runtime is to add no GPU of its own -- which is
            every time but when `--gpus` is what hands them out, that being docker saying
            which GPUs in this same variable.
        """
        # No account inside the image answers to the user it runs as, so home is said
        # outright, and away from the workspace: what a command caches is not the project's.
        said = {"HOME": "/tmp", **self._config.env}  # noqa: S108
        if visible:
            # Last, so nothing outranks it. A daemon whose default runtime is NVIDIA's hands
            # an image that sets this to `all` every GPU it has, asked for or not; `void` is
            # the value that runtime reads as none of its own, leaving only the devices the
            # daemon itself was asked for by name.
            said["NVIDIA_VISIBLE_DEVICES"] = "void"
        return [
            word for key, value in said.items() for word in ("--env", f"{key}={value}")
        ]

    def _resources(self) -> list[str]:
        """What it may take of the host, and what it runs under, GPUs aside."""
        config = self._config
        said: list[str] = []
        if config.cpus is not None:
            said += ["--cpus", f"{config.cpus:g}"]
        if config.memory is not None:
            said += ["--memory", str(config.memory)]
        if config.shm_size is not None:
            said += ["--shm-size", str(config.shm_size)]
        if config.runtime:
            said += ["--runtime", config.runtime]
        if config.network:
            said += ["--network", config.network]
        return said

    def _gpus(self) -> tuple[list[str], bool]:
        """The GPUs it is given, and whether they are given by name.

        Returns:
          The flags, none for a container given none, and True where they name each device.
        """
        gpus = self._config.gpus
        if not gpus:
            return [], False
        wanted = ("all",) if gpus == "all" else gpus
        if {f"{_CDI}={one}" for one in wanted} <= self._devices():
            # By name, where the daemon lists them: a device is the daemon's own to hand
            # out, needing no runtime of NVIDIA's to be its default.
            return [
                word for one in wanted for word in ("--device", f"{_CDI}={one}")
            ], True
        # Quoted, since docker reads the value as a CSV row and two ids are two fields of it
        # otherwise.
        ids = ",".join(wanted)
        return ["--gpus", "all" if gpus == "all" else f'"device={ids}"'], False

    def _devices(self) -> set[str]:
        """The devices the daemon can hand a container by name, or none it would say."""
        listed = self._info().get("DiscoveredDevices")
        if not isinstance(listed, list):
            return set()  # a daemon too old to list any, or one listing none
        return {
            str(one.get("ID"))
            for one in cast("list[dict[str, Any]]", listed)
            if one.get("Source") == "cdi"
        }

    def _info(self) -> dict[str, Any]:
        """What the daemon says of itself, asked once, or nothing where it would not say."""
        if self._told is None:
            try:
                self._told = info(str(self._endpoint))
            except OSError:
                self._told = {}
        return self._told

    def _whose(self, workspace: str) -> str:
        """Who the container runs as: whoever owns the workspace, as `uid:gid`.

        This user, on a daemon that is this machine's -- which for one running rootless, as
        this user, is the container's own root. On another, the owner of the workspace on
        *its* host, asked of a container of the same image given the same directory -- which
        is also what finds that there is no such directory there, since a bind mount of
        nothing is one docker refuses.

        Raises:
          FileNotFoundError: If the daemon's host has no such directory.
          RuntimeError: If no container of the image could be asked.
        """
        if self._endpoint.here:
            security = cast("list[str]", self._info().get("SecurityOptions") or [])
            if any("name=rootless" in one for one in security):
                return "0:0"
            return f"{os.getuid()}:{os.getgid()}"
        asked = subprocess.run(
            self._endpoint.docker(
                "run",
                "--rm",
                "--label",
                f"{_LABEL}={os.getuid()}",
                "--network",
                "none",
                "--mount",
                _bound(workspace),
                self._config.image,
                *python_command(["-c", _OWNER, workspace]),
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        # The last line, since an image's entrypoint may have said something first.
        owner = _OWNED.search(asked.stdout)
        if asked.returncode == 0 and owner is not None:
            return f"{owner[1]}:{owner[2]}"
        why = asked.stderr.strip()
        if "bind source path does not exist" in why:
            raise FileNotFoundError(
                errno.ENOENT,
                f"no directory to give the container on {self._endpoint}",
                workspace,
            )
        raise RuntimeError(
            f"could not start a container of {self._config.image} on {self._endpoint}: "
            f"{why or asked.stdout.strip()}"
        )


def _bound(workspace: str) -> str:
    """The `--mount` giving a container the workspace at the path it already has.

    Written as the CSV row docker reads it as, so a path holding a comma or a quote is one
    field rather than several.
    """
    row = io.StringIO()
    csv.writer(row, lineterminator="").writerow(
        ["type=bind", f"source={workspace}", f"target={workspace}"]
    )
    return row.getvalue()
