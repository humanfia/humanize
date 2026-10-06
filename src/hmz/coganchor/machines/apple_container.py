"""A container of Apple's `container` on this Mac, holding the workspace at the path it has here.

Apple's `container` runs each container as a small Linux virtual machine of its own. The project
directory is mounted into it rather than copied, and the container runs as this user, so what a
turn writes there is this user's file in this user's directory and survives the container it
was written from. Everything else -- the tools, the interpreters, the libraries a command
reaches for -- is the image's, which is what the isolation is.

It is this Mac's and no other's: `container` has no daemon elsewhere to point at and no GPU to
hand a container, so where a docker container names its daemon (:mod:`.docker`), one of these
names nothing. What a container may take of the Mac -- CPUs, memory -- is said in the setting
and written on the container as labels, under the names a docker container carries them by, so
that whoever shares the Mac out can read back what is already taken with :func:`allocations`.

Driven through the `container` command rather than a client library, because that is what a
turn reaches the container through: coganchor's `apple-container://` target runs its own half
over `container exec`, and one machine is best spoken to in one voice.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import AnchorConfig
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE
from hmz.coganchor.proto import path_spellings
from hmz.coganchor.transport import APPLE, Road, Target, python_command

from .base import MachineBase, MachineConfig
from .docker import CPUS, MEMORY, Allocation

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The command that drives Apple's containers.
CONTAINER = "container"

#: What the container does while the turns come and go: nothing, in the interpreter
#: coganchor's target half needs, looked for the way that half looks for it -- as a docker
#: container idles, and for the same reason: an image holding no Python is a container that
#: stops as it starts, and so a flow that fails where it is set up rather than a turn later.
_IDLE = tuple(python_command(["-c", "import time; time.sleep(2**31)"]))

#: Marks a container as one of ours, and whose: the label a docker container carries, read by
#: whoever lists the containers, to whom the backends are not two things.
_LABEL = "humanize"

#: What `container` takes as a container's name, which is its id.
_NAMED = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+")

#: What a virtual machine's memory is sized in.
_MIB = 1 << 20


@dataclass(frozen=True, kw_only=True)
class AppleContainerConfig(MachineConfig):
    """What the container is run from.

    Attributes:
      image: The image to run, which needs `/bin/sh` and a Python of at least 3.12 for
        coganchor's target half, and whatever else the agent is expected to reach for.
      workspace: The project directory to give the container, defaulting to this directory.
        It is the directory itself that goes there, not a copy of it, so the work outlives
        the container.
      name: What to call the container, or None for a name of its own. A config that names
        its container brings up one at a time: a second agent given it while the first still
        holds the name is refused by `container`.
      cpus: How many CPUs its virtual machine has, or None for `container`'s default. Whole
        CPUs, since a virtual machine has no part of one.
      memory: How many bytes of memory, rounded up to a whole MiB, or None for `container`'s
        default.
      run_args: What else `container run` is told, ahead of the image. Said before
        humanize's own resources, which a later flag outranks.
      env: Variables to set in it.
      labels: Labels to put on it beside humanize's own, which are never taken from here:
        what a container holds is read back off those, and they say only what it was given.
    """

    image: str = "python:3.12"
    workspace: str | None = None
    name: str | None = None
    cpus: int | None = None
    memory: int | None = None
    run_args: tuple[str, ...] = ()
    # Left out of the hash, which the rest of the setting still answers for: a mapping has
    # none, and a frozen setting that could not be hashed is one no set could hold.
    env: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    labels: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)

    def __post_init__(self) -> None:
        """Refuses what `container` would refuse, where it is written rather than as it starts.

        Raises:
          ValueError: If the name is not one `container` takes, a limit is not more than
            nothing or not whole CPUs, or a variable or a label has no name.
        """
        if self.name is not None and not _NAMED.fullmatch(self.name):
            raise ValueError(f"unsupported container name {self.name!r}")
        # Read as whatever it was handed, so that `2.0` is two CPUs and `1.5` or `"2"` is
        # refused here rather than by `container` as the run starts.
        cpus = cast("object", self.cpus)
        if cpus is not None and (
            not isinstance(cpus, int | float) or int(cpus) != cpus
        ):
            raise ValueError(f"cpus must be a whole number, not {cpus!r}")
        for what, limit in (("cpus", self.cpus), ("memory", self.memory)):
            if limit is not None and limit <= 0:
                raise ValueError(f"{what} must be more than nothing, not {limit!r}")
        if self.cpus is not None:
            object.__setattr__(self, "cpus", int(self.cpus))
        if self.memory is not None:
            # Up to the whole MiB `container` sizes a virtual machine in: what it is handed
            # otherwise it rounds down, which is less than was asked for.
            object.__setattr__(self, "memory", -(-self.memory // _MIB) * _MIB)
        for key in (*self.env, *self.labels):
            if not key or "=" in key:
                raise ValueError(f"unsupported name {key!r}; expected one without '='")
        object.__setattr__(self, "run_args", tuple(str(one) for one in self.run_args))
        # Copies, so the caller's own dictionary changing later does not change the setting.
        object.__setattr__(self, "env", dict(self.env))
        object.__setattr__(self, "labels", dict(self.labels))

    @property
    def capabilities(self) -> frozenset[str]:
        """`remote`, `isolated`, `managed` and `linux`, as a docker container's are.

        `linux` because every one of these is a Linux virtual machine, on a Mac: it is what
        :meth:`AppleContainer.start` asks the container, and refuses one that says otherwise.
        And the anchor's own, since one is built for it every time.
        """
        return (
            frozenset({ISOLATED, "linux", MANAGED, REMOTE})
            | AnchorConfig().capabilities
        )

    def create(self) -> AppleContainer:
        """Builds the machine, without starting a container yet."""
        return AppleContainer(self)


def allocations(
    labels: Mapping[str, str] | None = None, *, seconds: float | None = None
) -> list[Allocation]:
    """What humanize's running containers on this Mac hold of it.

    Whoever started them: the Mac is shared out between everybody using it, and a container
    is holding its share whichever user's flow brought it up. `container` filters nothing, so
    every running container is listed and those that are not humanize's, or do not carry
    `labels`, are passed over here.

    Args:
      labels: Labels a container must also carry to be counted, such as the provider it was
        allocated from.
      seconds: How long the question may take, or None for as long as it does.

    Returns:
      One allocation per container: the CPUs and memory its virtual machine has, and the
      labels it was started with. None holds a GPU, there being none to hold.

    Raises:
      OSError: If the containers could not be listed, or were not in time.
    """
    listed = _asked([CONTAINER, "list", "--format", "json"], seconds)
    found: object = None
    if listed.returncode == 0:
        with contextlib.suppress(ValueError):
            found = json.loads(listed.stdout or "[]")
    if not isinstance(found, list):
        # Which is not the same as a Mac with nothing on it, and not answered as one.
        why = listed.stderr.strip() or listed.stdout.strip()
        raise OSError(
            "could not ask Apple's container what it runs: "
            f"{why or f'exit {listed.returncode}'}"
        )
    wanted = {_LABEL: None, **(labels or {})}
    held: list[Allocation] = []
    for one in cast("list[Any]", found):
        said = _labels_of(one)
        if all(
            key in said and value in (None, said[key]) for key, value in wanted.items()
        ):
            held.append(_allocation(one, said))
    return held


def _labels_of(listed: object) -> dict[str, str]:
    """The labels a container carries, as `container list` says them, or none."""
    if not isinstance(listed, dict):
        return {}
    config = cast("dict[str, Any]", listed).get("configuration")
    labels: object = (
        cast("dict[str, Any]", config).get("labels") if isinstance(config, dict) else {}
    )
    if not isinstance(labels, dict):
        return {}
    return {
        str(key): str(value) for key, value in cast("dict[Any, Any]", labels).items()
    }


def _allocation(listed: Mapping[str, Any], said: Mapping[str, str]) -> Allocation:
    """What one container holds: the size `container list` says its virtual machine has.

    Read off the virtual machine rather than only off its labels, as a docker container's
    is: one started with no size of its own still has one -- `container`'s default -- and
    holds it. Its labels are read only where `container` did not say.
    """
    config = cast("dict[str, Any]", listed.get("configuration") or {})
    resources: object = config.get("resources")
    sized = cast("dict[str, Any]", resources) if isinstance(resources, dict) else {}
    cpus = _number(sized.get("cpus"), float)
    memory = _number(sized.get("memoryInBytes"), int)
    return Allocation(
        name=str(config.get("id") or listed.get("id") or ""),
        cpus=_number(said.get(CPUS), float) if cpus is None else cpus,
        memory=_number(said.get(MEMORY), int) if memory is None else memory,
        gpus=(),
        labels=dict(said),
    )


def _number[N: (int, float)](said: object, kind: type[N]) -> N | None:
    """A label, or a size `container` said, read as the number it should hold, or None.

    Rather than raising: a label is anybody's to write on a container, and one written wrong
    on somebody else's must not stop every reader of the Mac from counting the rest.
    """
    if said is None or isinstance(said, bool):
        return None
    try:
        return kind(str(said))
    except ValueError:
        return None


def status(seconds: float | None = None) -> dict[str, Any]:
    """What Apple's container system says of itself, as `container system status` says it.

    Args:
      seconds: How long it may take, or None for as long as it does.

    Returns:
      Everything it said, which says it is running.

    Raises:
      OSError: If there is no `container` here, it could not be asked or did not answer in
        time, or it is not running -- in its own words.
    """
    said = _asked([CONTAINER, "system", "status", "--format", "json"], seconds)
    told: object = None
    with contextlib.suppress(ValueError):
        told = json.loads(said.stdout) if said.stdout.strip() else None
    held = cast("dict[str, Any]", told) if isinstance(told, dict) else {}
    if said.returncode or held.get("status") != "running":
        # Its own words, where it said any besides what it is.
        why = (
            said.stderr.strip()
            or (f"it is {held['status']}" if held.get("status") else "")
            or said.stdout.strip()
            or "it is not running"
        )
        raise OSError(f"could not ask Apple's container system what it has: {why}")
    return held


def capacity(said: Mapping[str, Any]) -> tuple[float, int]:
    """What this Mac has to give its containers: CPUs, and bytes of memory.

    The CPUs are those :func:`status` counts; the memory, which it does not say, is the Mac's
    own, every container being a virtual machine of this one.

    Args:
      said: What :func:`status` answered with.
    """
    host = said.get("host")
    cpus = cast("dict[str, Any]", host).get("cpus") if isinstance(host, dict) else None
    return (
        float(cpus or os.cpu_count() or 0),
        os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
    )


def _asked(argv: list[str], seconds: float | None) -> subprocess.CompletedProcess[str]:
    """Runs one question for `container`, with nothing on its stdin, for so long at most.

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


def mounted(workspace: str) -> list[str]:
    """The `--mount`s giving a container the workspace at the path it has, under each name.

    A Mac reaches `/tmp`, `/var` and `/etc` through `/private`, and coganchor's serving half
    folds the one spelling into the other wherever it runs -- so a workspace under either is
    mounted at both, and a path to it reads the same in the container whichever was written.

    Args:
      workspace: The directory, absolute.
    """
    return [
        word
        for spelled in path_spellings(workspace)
        for word in ("--mount", f"type=bind,source={workspace},target={spelled}")
    ]


class AppleContainer(MachineBase):
    """One container, and the mirror the agent works in while its turns land there."""

    _config: AppleContainerConfig

    def __init__(self, config: AppleContainerConfig) -> None:
        """Initializes a machine holding no container.

        Args:
          config: The image and the workspace the container is started with.
        """
        super().__init__(config)
        self._mirror: tempfile.TemporaryDirectory[str] | None = None

    def start(self) -> AnchorConfig:
        """Starts the container and asks it what it is holding.

        Returns:
          The anchor that reaches it, which names the workspace by the path it has here and
          the container by its name.

        Raises:
          FileNotFoundError: If there is no workspace directory to give the container, or no
            `container` to give it to.
          ValueError: If the workspace's path holds a comma, which `container` reads a mount
            as several fields at and has no way to quote.
          RuntimeError: If the container cannot be started -- an image with no shell in it, or
            none holding a Python new enough, is refused here. What `container` said is
            attached. Or if what came up is not the machine these settings promised.
          OSError: If the container cannot serve the workspace it was given, which is a turn
            that would fail on its first file, reported before the first turn instead.
        """
        config = self._config
        if shutil.which(CONTAINER) is None:
            raise FileNotFoundError(
                errno.ENOENT, "no container command here", CONTAINER
            )
        # `abspath` rather than `Path.resolve`: what is mounted is the directory named, and a
        # workspace reached through a symlink is not a request to mount what it points at.
        workspace = os.path.abspath(config.workspace or os.getcwd())  # noqa: PTH100, PTH109
        if not Path(workspace).is_dir():
            raise FileNotFoundError(
                errno.ENOENT, "no directory to give the container", workspace
            )
        if "," in workspace:
            raise ValueError(
                f"Apple's container cannot mount {workspace!r}: a path holding a comma"
            )
        # A mirror of its own, never the workspace, for the reason a docker container's is:
        # the target's copy *is* the workspace, mounted rather than mirrored.
        self._mirror = tempfile.TemporaryDirectory(
            prefix="humanize-", ignore_cleanup_errors=True
        )
        name = config.name or Path(self._mirror.name).name
        target = Target.parse(f"{APPLE}://{name}")
        try:
            started = subprocess.run(
                [
                    CONTAINER,
                    "run",
                    "--detach",
                    # Errors alone on its stderr: what it fetched and unpacked is not why it
                    # could not start.
                    "--progress",
                    "none",
                    # Where `container` writes the id of what it created, which is the one
                    # thing `stop` may remove: a name somebody else's container already had is
                    # a container this never made.
                    "--cidfile",
                    self._made(),
                    "--name",
                    name,
                    *self._labelled(),
                    # This user, whose files the workspace holds: the mount carries the
                    # ownership the Mac has, and what is written there is this user's again.
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "--workdir",
                    workspace,
                    *self._environment(),
                    *mounted(workspace),
                    *config.run_args,
                    *self._resources(),
                    config.image,
                    *_IDLE,
                ],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            if started.returncode != 0:
                # Raised here rather than below: everything in this block may have a
                # container behind it by now, and the handler is what takes it back down.
                raise RuntimeError(  # noqa: TRY301
                    f"could not start a container of {config.image}: "
                    f"{started.stderr.strip()}"
                )
            # A container made just now holds no bundle, whatever one of the same name was
            # given before it.
            Road.to(target).forget()
            anchor = AnchorConfig(
                target=target.describe(),
                workspace=workspace,
                shadow=str(Path(self._mirror.name) / "shadow"),
            )
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
            made = ""  # `container` never got as far as making one
        if made:
            subprocess.run(
                [CONTAINER, "delete", "--force", made],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        self._mirror.cleanup()

    def _made(self) -> str:
        """Where `container` says which container it made, beside the mirror it is named for."""
        assert self._mirror is not None  # noqa: S101 -- asked only once there is one
        return str(Path(self._mirror.name) / "container")

    def _labelled(self) -> list[str]:
        """The labels: the caller's, then whose it is and what it holds of the Mac."""
        config = self._config
        # Whose it is, so that sweeping up after a flow that was killed outright cannot reach
        # past this user; and none of humanize's own from the caller, as on a docker one.
        said = {
            key: value
            for key, value in config.labels.items()
            if key not in (_LABEL, CPUS, MEMORY)
        }
        said[_LABEL] = str(os.getuid())
        if config.cpus is not None:
            said[CPUS] = str(config.cpus)
        if config.memory is not None:
            said[MEMORY] = str(config.memory)
        return [
            word
            for key, value in said.items()
            for word in ("--label", f"{key}={value}")
        ]

    def _environment(self) -> list[str]:
        """Its variables: a home, and the caller's.

        No account inside the image answers to the user it runs as, so home is said outright,
        and away from the workspace: what a command caches is not the project's.
        """
        said = {"HOME": "/tmp", **self._config.env}  # noqa: S108
        return [
            word for key, value in said.items() for word in ("--env", f"{key}={value}")
        ]

    def _resources(self) -> list[str]:
        """What its virtual machine has of the Mac."""
        config = self._config
        said: list[str] = []
        if config.cpus is not None:
            said += ["--cpus", str(config.cpus)]
        if config.memory is not None:
            said += ["--memory", str(config.memory)]
        return said
