"""fence -- holding an agent CLI to the scopes a flow's `Permission` grants it.

A :class:`Fence` is the whole of what one agent's process tree may still reach: the paths it
may read, the paths it may change, and whether it may go online -- and, where it may not, the
few hosts it still has to reach to run at all. It is said in coganchor's own words rather than
in the flow API's, so that coganchor stays a layer that knows nothing of flows: a flow's
`Permission` is read into one by :func:`hmz.runtime.flowing.harnessing.fenced`, and anything
else that drives a CLI through coganchor may build one by hand.

A CLI that can be told what it may reach is told natively, and the part it was told is taken
off the fence by its driver (:meth:`hmz.coganchor.agents.AgentBase.natively`). Whatever is
left is put around it from outside by ``hmz internal fence`` (:mod:`hmz.coganchor.fence.wrap`):
Landlock for the filesystem and for TCP, a seccomp filter for every other kind of socket, and
for the network exactly one gate -- :class:`Proxy`, which passes a connection only to the hosts
the backend cannot run without.

What cannot be fenced is refused rather than run wider. A host with no Landlock -- macOS, a
kernel older than 5.13 or booted without it, one older than 6.7 where the network is to be cut
-- enforces nothing, and :func:`enforceable` is what says so before a session is opened.

Two holes are left by the kernel rather than by this module, and are said here so that nobody
reads the fence as closing them. Landlock does not govern connecting to a Unix socket, so a
socket some other process listens on -- a container daemon's, a session bus -- is a way to ask
that process to act for the agent, whatever the fence says. And where the network is cut, TCP
is cut by port rather than by address: the proxy's port is reachable on any address, which is
reachable by number only, there being no name resolution left inside the fence to find one.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Self, cast

from hmz.coganchor.fence.proxy import Proxy, permits

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "ALL",
    "DEVICES",
    "LEVELS",
    "NONE",
    "READ",
    "SYSTEM",
    "Fence",
    "Proxy",
    "enforceable",
    "permits",
    "wrapper",
]

#: How much of one scope a fence grants, ordered narrowest first. The same three words the flow
#: API's `PermissionKind` is spelled with, so that one of those is one of these as it stands.
NONE: Final = "none"
READ: Final = "read"
ALL: Final = "all"
LEVELS: Final = (NONE, READ, ALL)

#: What any program needs to read to run at all, granted however little the system scope is:
#: the programs and the libraries they load, and the handful of files under `/etc` that the C
#: library, a TLS stack and a resolver read before they do anything -- the certificates, who
#: the user is, the time zone, where a host is. `/proc` and `/sys` are how a process learns
#: about itself and the machine, and a runtime that cannot read `/proc/self` cannot start;
#: they are read-only, and `/proc` shows only what the kernel's own ptrace check lets a
#: process of this user see. `/opt` is not among them: a CLI installed there is granted its
#: own install tree, and nothing else under it is anybody's minimum.
SYSTEM: Final = (
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib32",
    "/lib64",
    "/libx32",
    "/etc/ssl",
    "/etc/ca-certificates",
    "/etc/pki",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/host.conf",
    "/etc/gai.conf",
    "/etc/nsswitch.conf",
    "/etc/passwd",
    "/etc/group",
    "/etc/localtime",
    "/etc/timezone",
    "/etc/os-release",
    "/etc/ld.so.cache",
    "/etc/ld.so.conf",
    "/etc/ld.so.conf.d",
    "/etc/alternatives",
    "/proc",
    "/sys",
)

#: What any program needs to write to run at all, granted however little is: the devices a
#: program writes to without meaning to change anything -- the bit bucket, the randomness, the
#: terminal it was started on -- and `/dev/shm`, which is where POSIX shared memory lives and
#: where a supervisor keeps the credentials it answers reads with.
DEVICES: Final = (
    "/dev/null",
    "/dev/zero",
    "/dev/full",
    "/dev/random",
    "/dev/urandom",
    "/dev/tty",
    "/dev/pts",
    "/dev/ptmx",
    "/dev/shm",  # noqa: S108 -- the device, not a temporary file
)


def _rank(level: str) -> int:
    try:
        return LEVELS.index(str(level))
    except ValueError:
        raise ValueError(
            f"a scope is one of {', '.join(LEVELS)}, not {level!r}"
        ) from None


def _normal(paths: Iterable[str | os.PathLike[str]]) -> tuple[str, ...]:
    """Paths as a fence holds them: absolute, with no `..`, each once, in the order given."""
    return tuple(
        dict.fromkeys(
            os.path.normpath(os.path.abspath(os.fspath(one)))  # noqa: PTH100
            for one in paths
        )
    )


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _ours() -> tuple[str, ...]:
    """Where the Python running humanize is, and humanize itself.

    Read inside every fence, because humanize's own supervisors run inside it: a turn under a
    provider is `hmz internal cred` around the CLI, and a CLI given a flow's hooks or tools
    starts `hmz internal hook` and `hmz internal tools`. An interpreter uv installed lives
    under the user's home, and a checkout installed in place is wherever it was checked out.
    """
    executable = Path(sys.executable).resolve()
    return (
        sys.prefix,
        sys.base_prefix,
        sys.exec_prefix,
        sys.base_exec_prefix,
        str(executable.parent.parent),
        # The directory `hmz` is imported from, not `hmz` alone: Python has to list it
        # to find the package, and a checkout installed in place is on `sys.path` as
        # its `src`.
        str(Path(__file__).resolve().parents[3]),
    )


@dataclass(frozen=True, slots=True)
class Fence:
    """What one agent's process tree may reach, and nothing else.

    A path grants everything beneath it. What is in neither list cannot be opened, listed or
    run; what is in `read` alone can be opened, listed and run and not changed; what is in
    `write` can be changed in every way -- a path in both is in `write`, which is the wider.
    `/` in `write` is the whole filesystem, and a fence that grants that and the network too
    fences nothing: :attr:`open`, which needs nothing put around the CLI at all.

    Built from the four scopes by :meth:`of`, which adds the minimum every program needs to
    run; made wider by :meth:`granting` and narrower by nothing, since a fence that can only
    widen once built is one nobody can quietly tighten into a CLI that cannot start.

    Attributes:
      read: Absolute paths that may be read, listed and executed.
      write: Absolute paths that may be read and changed.
      online: Whether the network is unrestricted. False cuts it off below the CLI and leaves
        one way out, a proxy that passes only `hosts`.
      hosts: What that proxy lets through while `online` is False, as
        :func:`~hmz.coganchor.fence.proxy.permits` reads an allow-list: an exact host, a
        `*.suffix`, or a `host:port`. Meaningless while `online` is True.
      tmp: A directory of this fence's own for everything the CLI writes as scratch --
        exported as `TMPDIR`, `TMP` and `TEMP`, and where caches the fence would not let it
        write at home are pointed -- or "" for the wrapper to make one for the one run and
        remove it after.
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    online: bool = True
    hosts: tuple[str, ...] = ()
    tmp: str = ""

    def __post_init__(self) -> None:
        write = _normal(self.write)
        object.__setattr__(self, "write", write)
        object.__setattr__(
            self, "read", tuple(one for one in _normal(self.read) if one not in write)
        )
        object.__setattr__(self, "hosts", tuple(dict.fromkeys(self.hosts)))

    @classmethod
    def of(
        cls,
        *,
        local: str,
        user: str,
        system: str,
        online: bool,
        workdir: str | os.PathLike[str],
        home: str | os.PathLike[str],
        cwd: str | os.PathLike[str] = "",
        hosts: Iterable[str] = (),
        read: Iterable[str | os.PathLike[str]] = (),
        write: Iterable[str | os.PathLike[str]] = (),
    ) -> Fence:
        """The fence four scopes come to, with the minimum every program needs to run.

        Each scope is a root -- `system` is `/`, `user` the home directory, `local` the
        workdir and the directory the session works in where that is somewhere else -- and a
        level: `read` puts the root in :attr:`read`, `all` puts it in :attr:`write`, and `none`
        leaves it out. Then the minimum is added, whatever the levels were: :data:`SYSTEM` and
        the Python humanize runs on to read, :data:`DEVICES` to write.

        The scopes must nest, `local` at least `user` and `user` at least `system`, because
        a root is granted with everything beneath it and nothing beneath a grant can be taken
        back out of it: a home that may be written holds a workdir that could then not be kept
        read-only.

        Args:
          local: How much of the workdir may be touched, as one of :data:`LEVELS`.
          user: How much of the home directory.
          system: How much of everything else.
          online: Whether the network is unrestricted.
          workdir: The workdir.
          home: The home directory of the user the agent runs as.
          cwd: Where the session works, where that is not the workdir; granted as the
            workdir is.
          hosts: What the proxy passes while `online` is False.
          read: More paths to read, over the minimum: a CLI's own programs.
          write: More paths to write: a CLI's own state.

        Returns:
          The fence.

        Raises:
          ValueError: If a level is not one of :data:`LEVELS`, or the scopes do not nest.
        """
        ranks = [_rank(one) for one in (local, user, system)]
        if not ranks[0] >= ranks[1] >= ranks[2]:
            raise ValueError(
                f"scopes must nest, local >= user >= system; got local={local}, "
                f"user={user}, system={system}"
            )
        scopes = [
            (os.sep, system),
            (os.fspath(home), user),
            (os.fspath(workdir), local),
        ]
        if cwd:
            scopes.append((os.fspath(cwd), local))
        reading = [root for root, level in scopes if str(level) == READ]
        writing = [root for root, level in scopes if str(level) == ALL]
        return cls(
            read=_normal((*SYSTEM, *_ours(), *reading, *read)),
            write=_normal((*DEVICES, *writing, *write)),
            online=online,
            hosts=tuple(hosts),
        )

    @property
    def open(self) -> bool:
        """Whether this fences nothing at all: the whole filesystem to write, and the network."""
        return self.online and os.sep in self.write

    @property
    def everything(self) -> bool:
        """The same as :attr:`open`, under the name a reader of "grants everything" looks for."""
        return self.open

    def granting(
        self,
        *,
        read: Iterable[str | os.PathLike[str]] = (),
        write: Iterable[str | os.PathLike[str]] = (),
        hosts: Iterable[str] = (),
    ) -> Fence:
        """This fence with more let through.

        Args:
          read: Paths to read as well.
          write: Paths to write as well.
          hosts: Hosts the proxy passes as well.

        Returns:
          The wider fence, which is this one where nothing was named.
        """
        return dataclasses.replace(
            self,
            read=(*self.read, *_normal(read)),
            write=(*self.write, *_normal(write)),
            hosts=(*self.hosts, *hosts),
        )

    def without(self, *, filesystem: bool = False, network: bool = False) -> Fence:
        """What is left to fence from outside once part of it is fenced some other way.

        What a driver whose CLI enforces part of this fence itself returns from
        :meth:`hmz.coganchor.agents.AgentBase.natively`: the filesystem taken off leaves the
        whole of it writable here, the network taken off leaves it online here. Both taken off
        leaves a fence that is :attr:`open`, which puts nothing around the CLI.

        Args:
          filesystem: Whether the paths are enforced elsewhere.
          network: Whether the network is.

        Returns:
          The remainder.
        """
        return dataclasses.replace(
            self,
            read=() if filesystem else self.read,
            write=(os.sep,) if filesystem else self.write,
            online=self.online or network,
        )

    def allows(self, path: str | os.PathLike[str], *, write: bool = False) -> bool:
        """Whether a path is inside what this fence grants.

        Args:
          path: The path, which is taken as it is written: a link in it is not followed.
          write: Whether it is to be written as well as read.

        Returns:
          Whether some root this fence grants holds it.
        """
        (held,) = _normal((path,))
        roots = self.write if write else (*self.write, *self.read)
        return any(_under(held, root) for root in roots)

    def dumps(self) -> str:
        """This fence as JSON, which is what ``hmz internal fence --policy`` takes."""
        return json.dumps(dataclasses.asdict(self), separators=(",", ":"))

    @classmethod
    def loads(cls, said: str) -> Self:
        """A fence out of what :meth:`dumps` wrote.

        Args:
          said: The JSON.

        Returns:
          The fence.

        Raises:
          ValueError: If it is not a fence: not JSON, not an object, or with a field that is
            not a fence's or of the wrong kind.
        """
        loaded: object = json.loads(said)
        if not isinstance(loaded, dict):
            raise ValueError("a fence is a JSON object")  # noqa: TRY004 -- a bad policy
        held = cast("dict[str, Any]", loaded)
        names = {one.name for one in dataclasses.fields(cls)}
        if unknown := set(held) - names:
            raise ValueError(f"not a fence's: {', '.join(sorted(unknown))}")
        for name in ("read", "write", "hosts"):
            listed: object = held.get(name, [])
            if not isinstance(listed, list) or not all(
                isinstance(one, str) for one in cast("list[object]", listed)
            ):
                raise ValueError(f"a fence's {name} is a list of strings")
            held[name] = tuple(cast("list[str]", listed))
        if not isinstance(held.get("online", True), bool):
            raise ValueError("a fence's online is true or false")  # noqa: TRY004
        if not isinstance(held.get("tmp", ""), str):
            raise ValueError("a fence's tmp is a path")  # noqa: TRY004
        return cls(**held)


def enforceable(*, net: bool) -> bool:
    """Whether this host can put a fence around a process at all.

    Args:
      net: Whether the fence cuts the network as well as the filesystem.

    Returns:
      Whether Landlock is here -- at an ABI that governs TCP where `net` is asked for, with
      the socket filter that shuts every other protocol loadable beside it.
    """
    from hmz.coganchor.linux import landlock

    if not landlock.available(net=net):
        return False
    if not net:
        return True
    try:
        importlib.import_module("hmz.coganchor.linux.seccomp")
    except (ImportError, OSError, RuntimeError):
        return False
    return True


def wrapper(fence: Fence) -> list[str]:
    """The command a program is put inside a fence with, less the program.

    Args:
      fence: The fence.

    Returns:
      ``hmz internal fence --policy=... --``, run by the Python running this, to be followed
      by the program and its arguments.
    """
    return [
        sys.executable,
        "-m",
        "hmz",
        "internal",
        "fence",
        f"--policy={fence.dumps()}",
        "--",
    ]
