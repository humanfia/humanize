"""A container of one image as the one task of a service on a docker swarm, wherever it lands.

What :mod:`.docker` is for one daemon, this is for a swarm: the container is not started by
naming a daemon but asked of a manager, as a service of one replica that is never restarted,
and the swarm's scheduler puts it on whichever node has room for what it reserves and answers
to its constraints. Where it landed is only known once it has: the task says which node, and
which container on it, and from then on the container is reached the way any other is -- by
`docker exec` against the daemon holding it, which is the manager's own where the task landed
on the manager, and the node's daemon over ssh where it did not.

The workspace is a bind mount of the path it already has, as it is for one daemon -- of the
node's host now, which nobody can say in advance. So a swarm whose tasks may land on several
nodes has to have the directory at the same path on every one of them: a shared filesystem, or
constraints keeping the tasks where it is. A task that lands where it is not is refused by its
node, and said so.

What the service reserves of a node is what it is limited to as well, so that what the
scheduler counts as taken is what the container can take; and the same labels a container of
:mod:`.docker` carries are on the service, so that what a swarm's services hold is read back the
same way.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import AnchorConfig
from hmz.coganchor.places import ISOLATED, MANAGED, REMOTE
from hmz.coganchor.transport import Endpoint, Road, Target, python_command

from .base import MachineBase, MachineConfig
from .docker import CPUS, GPUS, MEMORY, Allocation, bound, info, whose

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "Node",
    "Placed",
    "Swarm",
    "SwarmConfig",
    "Unplaced",
    "nodes",
    "services",
    "swarm_of",
]

#: What the task does while the turns come and go, as a container of :mod:`.docker` does.
_IDLE = tuple(python_command(["-c", "import time; time.sleep(2**31)"]))

#: Marks a service as one of ours, and whose: the label :mod:`.docker` marks a container with.
_LABEL = "humanize"

#: The states a task has left for good without running, as the swarm names them.
_OVER = frozenset({"complete", "shutdown", "failed", "rejected", "orphaned", "remove"})

#: What the scheduler says of a task no node has room for, or none answers the constraints of.
_NO_NODE = "no suitable node"

#: How often a task that has not yet landed is asked after.
_POLL = 0.5


class Unplaced(RuntimeError):  # noqa: N818 -- named for what happened, as the rest are
    """No node of the swarm took the task: none had room for it, or none answered.

    Its message is the scheduler's own, beside how long it was given.
    """


@dataclass(frozen=True, kw_only=True)
class SwarmConfig(MachineConfig):
    """What the service is created from, on which swarm, and how its nodes are reached.

    Attributes:
      image: The image to run, which needs `/bin/sh` and a Python of at least 3.12, and has
        to be one every node it may land on can pull.
      workspace: The project directory to give the task, absolute, as every node it may land
        on names it.
      endpoint: A manager of the swarm, as :class:`~hmz.coganchor.transport.Endpoint` reads
        one: `local` for a swarm this machine manages.
      name: What to call the service, or None for a name of its own.
      user: Who the task runs as, `uid:gid`, or None for whoever owns the workspace -- asked
        of the manager's host, as :mod:`.docker` asks a daemon's.
      cpus: How many CPUs it reserves and may use, or None for no reservation and no limit.
      memory: How many bytes of memory, likewise.
      generic: The generic resources it reserves of its node, as `(kind, how many)`: what a
        node advertises its GPUs as, and how many of them.
      constraints: Where it may be placed, as `--constraint` takes each.
      nodes: The daemon of each node, by its host name, spelled as `endpoint` is, for a node
        not reached as `ssh://<its address>`.
      traced: Whether it may borrow its processes' descriptors, which a supervised harness
        does: `CAP_SYS_PTRACE`.
      run_args: What else `docker service create` is told, ahead of the image.
      env: Variables to set in it.
      labels: Labels to put on the service beside humanize's own.
      placing: How long, in seconds, the task may wait for a node with room before it is
        given up on.
      starting: How long, in seconds, it may take to be running once it has a node --
        pulling its image among it.
    """

    image: str = "python:3.12"
    workspace: str
    endpoint: str = "local"
    name: str | None = None
    user: str | None = None
    cpus: float | None = None
    memory: int | None = None
    generic: tuple[tuple[str, int], ...] = ()
    constraints: tuple[str, ...] = ()
    nodes: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    traced: bool = False
    run_args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    labels: Mapping[str, str] = field(default_factory=dict[str, str], hash=False)
    placing: float = 30.0
    starting: float = 600.0

    def __post_init__(self) -> None:
        """Refuses what the swarm would refuse, where it is written rather than as it starts.

        Raises:
          ValueError: If an endpoint cannot be read, the workspace is not absolute, a limit
            or a reservation is not more than nothing, or a variable or a label has no name.
        """
        Endpoint.parse(self.endpoint)
        for one in self.nodes.values():
            Endpoint.parse(one)
        if not self.workspace.startswith("/"):
            raise ValueError(
                f"a workspace on a swarm is a path on its nodes, so it has to be an "
                f"absolute one, not {self.workspace!r}"
            )
        for what, limit in (("cpus", self.cpus), ("memory", self.memory)):
            if limit is not None and limit <= 0:
                raise ValueError(f"{what} must be more than nothing, not {limit!r}")
        for kind, many in self.generic:
            if not kind or many <= 0:
                raise ValueError(f"unsupported generic resource {kind}={many}")
        for key in (*self.env, *self.labels):
            if not key or "=" in key:
                raise ValueError(f"unsupported name {key!r}; expected one without '='")
        object.__setattr__(self, "nodes", dict(self.nodes))
        object.__setattr__(self, "env", dict(self.env))
        object.__setattr__(self, "labels", dict(self.labels))

    @property
    def capabilities(self) -> frozenset[str]:
        """`remote`, `isolated`, `managed` and `linux`: a container's, for a container's reasons."""
        return (
            frozenset({ISOLATED, "linux", MANAGED, REMOTE})
            | AnchorConfig().capabilities
        )

    def create(self) -> Swarm:
        """Builds the backend, without creating a service yet."""
        return Swarm(self)


@dataclass(frozen=True, slots=True)
class Node:
    """One node of a swarm, as its manager says it.

    Attributes:
      id: The node's id.
      hostname: Its host name.
      address: The address the swarm reaches it at.
      ready: Whether it may be given a task: ready, and neither drained nor paused.
      cpus: How many CPUs it has.
      memory: How many bytes of memory.
      resources: The generic resources it advertises, by kind: how many of each.
    """

    id: str
    hostname: str
    address: str
    ready: bool
    cpus: float
    memory: int
    resources: Mapping[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True, slots=True)
class Placed:
    """Where a task landed: its node, and its container there.

    Attributes:
      node: The node.
      container: The container's id.
      daemon: The daemon holding it, as this machine reaches it.
    """

    node: Node
    container: str
    daemon: Endpoint


def swarm_of(told: Mapping[str, Any], where: str) -> str:
    """The id of the node a daemon is, where it manages an active swarm.

    Args:
      told: What `docker info` said of it.
      where: The daemon, as a message names it.

    Raises:
      OSError: If it is in no swarm, or in one it cannot manage.
    """
    swarm = cast("dict[str, Any]", told.get("Swarm") or {})
    state = str(swarm.get("LocalNodeState") or "inactive")
    if state != "active":
        raise OSError(f"{where} is in no active swarm: its swarm is {state}")
    if not swarm.get("ControlAvailable"):
        raise OSError(
            f"{where} is a worker of its swarm, and only a manager can be asked"
        )
    return str(swarm.get("NodeID") or "")


def nodes(endpoint: str = "local", seconds: float | None = None) -> list[Node]:
    """Every node of the swarm a manager manages.

    Args:
      endpoint: The manager, spelled as :attr:`SwarmConfig.endpoint` is.
      seconds: How long asking may take all told, or None for as long as it does.

    Raises:
      ValueError: If the endpoint cannot be read.
      OSError: If the manager cannot be asked, or did not answer in time.
    """
    where = Endpoint.parse(endpoint)
    began = time.monotonic()
    listed = _asked(where.docker("node", "ls", "--quiet"), seconds)
    if listed.returncode != 0:
        raise OSError(f"could not ask {where} for its nodes: {listed.stderr.strip()}")
    ids = listed.stdout.split()
    if not ids:
        return []
    left = None if seconds is None else seconds - (time.monotonic() - began)
    if left is not None and left <= 0:
        raise OSError(errno.ETIMEDOUT, f"{where} did not answer within {seconds:g}s")
    return [_node(one) for one in _inspected(where, ["node", "inspect", *ids], left)]


def services(
    endpoint: str = "local",
    labels: Mapping[str, str] | None = None,
    *,
    seconds: float | None = None,
) -> list[Allocation]:
    """What humanize's services on a swarm hold of it, whoever created them.

    Args:
      endpoint: The manager, spelled as :attr:`SwarmConfig.endpoint` is.
      labels: Labels a service must also carry to be counted, such as its runtime's.
      seconds: How long each question may take, or None for as long as it does.

    Returns:
      One allocation per service, read off the labels it was created with, under its name.

    Raises:
      ValueError: If the endpoint cannot be read.
      OSError: If the manager cannot be asked, or did not answer in time.
    """
    where = Endpoint.parse(endpoint)
    wanted = [f"label={_LABEL}"]
    wanted += [f"label={key}={value}" for key, value in (labels or {}).items()]
    listed = _asked(
        where.docker(
            "service",
            "ls",
            "--quiet",
            *(word for one in wanted for word in ("--filter", one)),
        ),
        seconds,
    )
    if listed.returncode != 0:
        raise OSError(f"could not ask {where} what it runs: {listed.stderr.strip()}")
    ids = listed.stdout.split()
    if not ids:
        return []
    return [
        _allocation(one)
        for one in _inspected(where, ["service", "inspect", *ids], seconds)
    ]


def _inspected(
    where: Endpoint, argv: Sequence[str], seconds: float | None
) -> list[dict[str, Any]]:
    """What an `inspect` said, less whatever went between listing it and asking.

    Raises:
      OSError: If it could not be asked, or said something else it could not do.
    """
    said = _asked(where.docker(*argv), seconds)
    trouble = [
        line
        for line in said.stderr.splitlines()
        if line.strip() and "no such" not in line.lower()
    ]
    try:
        if said.returncode != 0 and trouble:
            raise ValueError(trouble)  # noqa: TRY301 -- answered with the parse failure below
        return cast("list[dict[str, Any]]", json.loads(said.stdout or "[]"))
    except ValueError as why:
        raise OSError(f"could not ask {where}: {said.stderr.strip()}") from why


def _node(inspected: Mapping[str, Any]) -> Node:
    """One node, as `docker node inspect` said it."""
    spec = cast("dict[str, Any]", inspected.get("Spec") or {})
    described = cast("dict[str, Any]", inspected.get("Description") or {})
    status = cast("dict[str, Any]", inspected.get("Status") or {})
    has = cast("dict[str, Any]", described.get("Resources") or {})
    resources: dict[str, int] = {}
    for one in cast("list[dict[str, Any]]", has.get("GenericResources") or []):
        discrete = cast("dict[str, Any]", one.get("DiscreteResourceSpec") or {})
        named = cast("dict[str, Any]", one.get("NamedResourceSpec") or {})
        if kind := str(discrete.get("Kind") or ""):
            resources[kind] = resources.get(kind, 0) + int(discrete.get("Value") or 0)
        elif kind := str(named.get("Kind") or ""):
            resources[kind] = resources.get(kind, 0) + 1
    address = str(status.get("Addr") or "")
    if address in ("", "0.0.0.0"):  # noqa: S104 -- what a manager may say of itself
        manager = cast("dict[str, Any]", inspected.get("ManagerStatus") or {})
        address = str(manager.get("Addr") or "").rpartition(":")[0]
    return Node(
        id=str(inspected.get("ID") or ""),
        hostname=str(described.get("Hostname") or ""),
        address=address,
        ready=status.get("State") == "ready" and spec.get("Availability") == "active",
        cpus=int(has.get("NanoCPUs") or 0) / 1e9,
        memory=int(has.get("MemoryBytes") or 0),
        resources=resources,
    )


def _allocation(inspected: Mapping[str, Any]) -> Allocation:
    """What one service holds, as `docker service inspect` said it."""
    spec = cast("dict[str, Any]", inspected.get("Spec") or {})
    said = {
        str(key): str(value)
        for key, value in cast("dict[str, Any]", spec.get("Labels") or {}).items()
    }

    def number[N: (int, float)](label: str | None, kind: type[N]) -> N | None:
        try:
            return kind(label) if label is not None else None
        except ValueError:
            return None  # a label is anybody's to write, and one written wrong counts nothing

    gpus = said.get(GPUS, "")
    return Allocation(
        name=str(spec.get("Name") or inspected.get("ID") or ""),
        cpus=number(said.get(CPUS), float),
        memory=number(said.get(MEMORY), int),
        gpus=tuple(one for one in gpus.split(",") if one),
        labels=said,
    )


def _asked(argv: list[str], seconds: float | None) -> subprocess.CompletedProcess[str]:
    """Runs one question for a manager, with nothing on its stdin, for so long at most.

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


class Swarm(MachineBase):
    """One service of one task, and the mirror the agent works in while its turns land there."""

    _config: SwarmConfig

    def __init__(self, config: SwarmConfig) -> None:
        """Initializes a backend holding no service.

        Args:
          config: The image, the workspace and the swarm the service is created on.
        """
        super().__init__(config)
        self._endpoint = Endpoint.parse(config.endpoint)
        self._mirror: tempfile.TemporaryDirectory[str] | None = None
        self._service = ""
        self._told: dict[str, Any] | None = None
        self.placed: Placed | None = None

    def start(self) -> AnchorConfig:
        """Creates the service, waits for its task to run, and asks it what it is holding.

        Returns:
          The anchor that reaches it: the workspace by its path on the node, and the
          container by a target carrying the daemon of that node.

        Raises:
          FileNotFoundError: If there is no `docker` here, or the node the task landed on --
            or the manager's host, asked whose the workspace is -- has no such directory.
          Unplaced: If no node took the task in time.
          RuntimeError: If the service could not be created, or its task failed, or what
            came up is not the machine these settings promised.
          OSError: If the manager or the node could not be asked, or the container cannot
            serve the workspace it was mounted.
        """
        config = self._config
        if shutil.which("docker") is None:
            raise FileNotFoundError(errno.ENOENT, "no docker command here", "docker")
        manager = swarm_of(self._info(), str(self._endpoint))
        self._mirror = tempfile.TemporaryDirectory(
            prefix="humanize-", ignore_cleanup_errors=True
        )
        name = config.name or Path(self._mirror.name).name
        try:
            user = config.user or whose(
                self._endpoint, config.image, config.workspace, self._info
            )
            made = subprocess.run(
                self._endpoint.docker(
                    "service",
                    "create",
                    "--detach",
                    "--quiet",
                    "--replicas",
                    "1",
                    "--restart-condition",
                    "none",
                    "--name",
                    name,
                    *self._labelled(),
                    "--user",
                    user,
                    "--workdir",
                    config.workspace,
                    *self._environment(),
                    "--mount",
                    bound(config.workspace),
                    *(("--cap-add", "SYS_PTRACE") if config.traced else ()),
                    *config.run_args,
                    *self._resources(),
                    config.image,
                    *_IDLE,
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            if made.returncode != 0:
                raise RuntimeError(  # noqa: TRY301 -- the handler takes down what was made
                    f"could not create a service of {config.image} on {self._endpoint}: "
                    f"{made.stderr.strip()}"
                )
            self._service = (
                made.stdout.strip().splitlines()[-1] if made.stdout else name
            )
            placed = self._landed(manager)
            self.placed = placed
            target = Target.parse(f"docker://{placed.container}@{placed.daemon}")
            Road.to(target).forget()
            anchor = AnchorConfig(
                target=target.describe(),
                workspace=config.workspace,
                shadow=str(Path(self._mirror.name) / "shadow"),
            )
            self.observe(anchor)
        except BaseException:
            self.stop()
            raise
        return anchor

    def stop(self) -> None:
        """Removes the service, and with it its task, leaving the workspace as it was left."""
        if self._mirror is None:
            return
        if self._service:
            with contextlib.suppress(OSError):
                _asked(self._endpoint.docker("service", "rm", self._service), 60.0)
            self._service = ""
        self._mirror.cleanup()

    def _landed(self, manager: str) -> Placed:
        """Waits for the task to be running, and says where.

        Args:
          manager: The id of the node the manager asked is, whose daemon is the one asked.

        Raises:
          Unplaced: If no node took it within :attr:`SwarmConfig.placing`, or none could
            ever have room for it.
          FileNotFoundError: If the node it landed on has no such workspace.
          RuntimeError: If it failed, or was not running within :attr:`SwarmConfig.starting`.
        """
        config = self._config
        began = time.monotonic()
        waiting = ""
        while True:
            task = self._task()
            status = cast("dict[str, Any]", task.get("Status") or {})
            state = str(status.get("State") or "new")
            said = str(status.get("Err") or status.get("Message") or state)
            if state == "running":
                container = str(
                    cast("dict[str, Any]", status.get("ContainerStatus") or {}).get(
                        "ContainerID"
                    )
                    or ""
                )
                return self._reached(str(task.get("NodeID") or ""), container, manager)
            if state in _OVER:
                if "bind source path does not exist" in said:
                    raise FileNotFoundError(
                        errno.ENOENT,
                        f"no directory to give the task on the node it landed on: {said}",
                        config.workspace,
                    )
                raise RuntimeError(f"the task of {self._service} is {state}: {said}")
            spent = time.monotonic() - began
            if state == "pending" and _NO_NODE in said:
                if not waiting:
                    waiting = said
                    self._could_ever(said)
                if spent > config.placing:
                    raise Unplaced(
                        f"no node took it within {config.placing:g}s: {said}"
                    )
            if spent > config.starting:
                raise RuntimeError(
                    f"the task of {self._service} was not running within "
                    f"{config.starting:g}s: it is {state}: {said}"
                )
            time.sleep(_POLL)

    def _task(self) -> dict[str, Any]:
        """The service's task as it is now, or one not yet made."""
        listed = _asked(
            self._endpoint.docker(
                "service", "ps", "--quiet", "--no-trunc", self._service
            ),
            60.0,
        )
        if listed.returncode != 0:
            raise OSError(
                f"could not ask {self._endpoint} after {self._service}: "
                f"{listed.stderr.strip()}"
            )
        ids = listed.stdout.split()
        if not ids:
            return {}
        found = _inspected(self._endpoint, ["inspect", "--type", "task", ids[0]], 60.0)
        return found[0] if found else {}

    def _could_ever(self, said: str) -> None:
        """Gives up now on a task no node of the swarm could ever have room for.

        Raises:
          Unplaced: If none could, saying what it reserves and what the most any has is.
        """
        config = self._config
        try:
            ready = [one for one in nodes(str(self._endpoint), 60.0) if one.ready]
        except OSError:
            return  # left to the scheduler, and to the wait
        fits = [
            one
            for one in ready
            if (config.cpus or 0) <= one.cpus
            and (config.memory or 0) <= one.memory
            and all(one.resources.get(kind, 0) >= many for kind, many in config.generic)
        ]
        if fits:
            return
        asked = [
            *((f"{config.cpus:g} CPUs",) if config.cpus else ()),
            *((f"{config.memory} bytes of memory",) if config.memory else ()),
            *(f"{many} {kind}" for kind, many in config.generic),
        ]
        most = (
            f"the most any of its {len(ready)} nodes that may take a task has is "
            f"{max(one.cpus for one in ready):g} CPUs and "
            f"{max(one.memory for one in ready)} bytes"
            if ready
            else "none of its nodes may take a task"
        )
        raise Unplaced(
            f"no node of the swarm has {' and '.join(asked) or 'room for it'}: {most} "
            f"({said})"
        )

    def _reached(self, node_id: str, container: str, manager: str) -> Placed:
        """The node a task landed on, and the daemon holding its container there.

        The one the setting names for its host where it names one; else the manager's own,
        reached as the manager is, where the task landed on the manager; else the node's over
        `ssh://<its address>`.
        """
        config = self._config
        found = [
            one
            for one in _inspected(self._endpoint, ["node", "inspect", node_id], 60.0)
            if one
        ]
        node = (
            _node(found[0])
            if found
            else Node(node_id, node_id, "", ready=True, cpus=0, memory=0)
        )
        if not container:
            raise RuntimeError(f"the task of {self._service} names no container")
        if node.hostname in config.nodes:
            daemon = Endpoint.parse(config.nodes[node.hostname])
        elif node_id == manager:
            daemon = self._endpoint
        elif node.address:
            daemon = Endpoint.parse(f"ssh://{node.address}")
        else:
            raise RuntimeError(
                f"the node {node.hostname} the task of {self._service} landed on says "
                "no address to reach it at: name it in the runtime's nodes"
            )
        return Placed(node, container, daemon)

    def _info(self) -> dict[str, Any]:
        """What the manager says of itself, asked once.

        Raises:
          OSError: If it could not be asked.
        """
        if self._told is None:
            self._told = info(str(self._endpoint))
        return self._told

    def _labelled(self) -> list[str]:
        """The labels: the caller's, then whose it is and what it holds of its node."""
        config = self._config
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
        if config.generic:
            said[GPUS] = ",".join(f"{kind}={many}" for kind, many in config.generic)
        return [
            word
            for key, value in said.items()
            for word in ("--label", f"{key}={value}")
        ]

    def _environment(self) -> list[str]:
        """Its variables: a home, the caller's, and no GPU but those it reserved."""
        said = {"HOME": "/tmp", **self._config.env}  # noqa: S108
        if not self._config.generic:
            # As for a container of one daemon's: NVIDIA's runtime hands an image that asks
            # for every GPU all of them, reserved or not.
            said["NVIDIA_VISIBLE_DEVICES"] = "void"
        return [
            word for key, value in said.items() for word in ("--env", f"{key}={value}")
        ]

    def _resources(self) -> list[str]:
        """What it reserves of its node, which is what it may take, and where it may land."""
        config = self._config
        said: list[str] = []
        if config.cpus is not None:
            said += [
                "--reserve-cpu",
                f"{config.cpus:g}",
                "--limit-cpu",
                f"{config.cpus:g}",
            ]
        if config.memory is not None:
            said += [
                "--reserve-memory",
                str(config.memory),
                "--limit-memory",
                str(config.memory),
            ]
        for kind, many in config.generic:
            said += ["--generic-resource", f"{kind}={many}"]
        for constraint in config.constraints:
            said += ["--constraint", constraint]
        return said
