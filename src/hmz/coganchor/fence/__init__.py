"""fence -- holding an agent CLI to the paths and network a flow's `Permission` grants it.

A :class:`Fence` is the whole of what one agent's process tree may still reach: the paths it
may read, the paths it may change, the paths beneath those it may only read or not reach at
all, and whether it may go online -- and, where it may not, the few hosts it still has to
reach to run at all. It is said in coganchor's own words rather than
in the flow API's, so that coganchor stays a layer that knows nothing of flows: a flow's
`Permission` is read into one by :func:`hmz.runtime.flowing.harnessing.fenced`, and anything
else that drives a CLI through coganchor may build one by hand.

A CLI that can be told what it may reach is told natively, and the part it was told is taken
off the fence by its driver (:meth:`hmz.coganchor.agents.AgentBase.natively`). Whatever is
left is put around it from outside by ``coganchor internal fence`` (:func:`wrapper`). On
Linux that is one of two backends, which `sandbox.backend` in this machine's settings chooses
between (:func:`chosen`): Landlock for the filesystem and for TCP, a seccomp filter for every
other kind of socket, and a supervisor that lets a socket listen on loopback and nowhere else;
or bubblewrap where Landlock cannot hold it, the paths mounted into a root of their own and the
network cut by a namespace of its own. On a Mac it is a Seatbelt profile for all of it. On all
three, the network has exactly one gate -- a proxy that passes a connection only to the hosts
the backend cannot run without.

What cannot be fenced is refused rather than run wider. A Linux host with no backend that
starts -- a kernel older than 5.13 or booted without Landlock, or older than 6.7 where the
network is to be cut, and no bubblewrap -- or a Mac already inside a sandbox of its own
enforces nothing, and :func:`enforceable` is what says so before a session is opened, having
asked `coganchor internal able`.

The person at the machine may instead name a CLI in `sandbox.native`, whose own sandbox then
holds what it can say of the fence around the commands the CLI runs, and nothing around the
CLI itself (:func:`natives`).

Holes are left by the kernel rather than by this module, and are said here so that nobody
reads the fence as closing them. Neither Landlock nor this profile governs connecting to a Unix
socket, so a socket some other process listens on -- a container daemon's, a session bus -- is
a way to ask that process to act for the agent, whatever the fence says; on a Mac, a Mach
service is the same. Where the network is cut on Linux, TCP is cut by port rather than by
address: the proxy's port is reachable on any address, which is reachable by number only,
there being no name resolution left inside the fence to find one. And where it is cut on a
Mac, Seatbelt cannot tell loopback from every address when a socket is bound: a program
inside may listen on every address, though it still connects to nothing but the proxy.
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import functools
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Self, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "AUTO",
    "BWRAP",
    "DARWIN_DEVICES",
    "DARWIN_SYSTEM",
    "DEVICES",
    "LANDLOCK",
    "LEVELS",
    "LINUX_DEVICES",
    "LINUX_SYSTEM",
    "NONE",
    "READ",
    "SYSTEM",
    "TEMPORARY",
    "WRITE",
    "Fence",
    "able",
    "chosen",
    "enforceable",
    "landlocked",
    "natives",
    "needs",
    "unheld",
    "wrapper",
]

#: What `sandbox.backend` may say: Landlock where it can hold a fence and bubblewrap otherwise,
#: or one of them alone. What `coganchor` is passed as `--sandbox`.
AUTO: Final = "auto"
LANDLOCK: Final = "landlock"
BWRAP: Final = "bwrap"

#: How much of a path a fence grants, ordered narrowest first: nothing, to read it, to change
#: it. The same three words the flow API's `Access` is spelled with, so that a rule's access
#: is one of these as it stands.
NONE: Final = "none"
READ: Final = "read"
WRITE: Final = "write"
LEVELS: Final = (NONE, READ, WRITE)

#: How a rule's path is anchored: at the root, at the home of the user the agent runs as, or
#: at the workdir.
_ROOT: Final = os.sep
_HOME: Final = "~"
_WORKDIR: Final = "."

#: What any program needs to read to run at all, granted however little the system scope is:
#: the programs and the libraries they load, and the handful of files under `/etc` that the C
#: library, a TLS stack and a resolver read before they do anything -- the certificates, who
#: the user is, the time zone, where a host is. `/sys` is how a process learns about the
#: machine, and is read-only; `/proc`, how it learns about itself, is written as well, and is
#: among :data:`LINUX_DEVICES`. `/opt` is not among them: a CLI installed there is granted its
#: own install tree, and nothing else under it is anybody's minimum.
LINUX_SYSTEM: Final = (
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
    "/sys",
)

#: The same on a Mac, where the libraries and frameworks are under `/System` as well as
#: `/usr`, `/bin/sh` reads which shell it is from `/private/var/select`, and `/etc/localtime`
#: leads into `/private/var/db/timezone`. `/Library` and `/opt` are not among them, for the
#: reason `/opt` is not on Linux -- except the developer tools. `/usr/bin/git`, `make`, `clang`
#: and `python3` on a Mac are Apple's `xcrun` shims, which follow
#: `/private/var/db/xcode_select_link` to the developer directory `xcode-select` chose and load
#: `libxcrun.dylib` and the real program from there; a fence that kept them out would have
#: `git log` fail with `xcrun: error: unable to load libxcrun` before it read anything. So the
#: link is read, and the two places it leads on any Mac that has the tools: the Command Line
#: Tools, and Xcode where it is installed -- the whole of `Xcode.app`, whose tools load its
#: `SharedFrameworks` and `Frameworks` beside `Contents/Developer`, with the plist its license
#: is checked against. A directory chosen anywhere else is added where the fence is drawn
#: (:func:`_developer`).
_XCODE_SELECT: Final = "/private/var/db/xcode_select_link"
DARWIN_SYSTEM: Final = (
    "/usr",
    "/bin",
    "/sbin",
    "/System",
    "/private/var/select",
    "/private/var/db/timezone",
    _XCODE_SELECT,
    "/Library/Developer/CommandLineTools",
    "/Library/Preferences/com.apple.dt.Xcode.plist",
    "/Applications/Xcode.app",
    "/etc/ssl",
    "/etc/resolv.conf",
    "/etc/hosts",
    "/etc/services",
    "/etc/protocols",
    "/etc/passwd",
    "/etc/group",
    "/etc/shells",
    "/etc/localtime",
)

#: What any program needs to write to run at all, granted however little is: the devices a
#: program writes to without meaning to change anything -- the bit bucket, the randomness, the
#: terminal it was started on -- `/dev/shm`, which is where POSIX shared memory lives and
#: where a supervisor keeps the credentials it answers reads with, and `/proc`. A runtime that
#: cannot read `/proc/self` cannot start, and a thread named by another is named by writing
#: `/proc/self/task/<tid>/comm` -- which glibc's `pthread_setname_np` does, and libcuda's
#: `cuInit` with it, giving up (304, `CUDA_ERROR_OPERATING_SYSTEM`) where it cannot. Landlock
#: cannot grant `/proc/self` to a whole process tree, it being one pid when the rules are
#: made, so it is `/proc`. The kernel's own checks still hold beneath it: another process is
#: reached only past the ptrace check, which Landlock confines to the fenced tree, and
#: `/proc/sys` only by root -- whom no fence holds anyway, there being calls besides opening
#: a file that change the machine.
LINUX_DEVICES: Final = (
    "/dev/null",
    "/dev/zero",
    "/dev/full",
    "/dev/random",
    "/dev/urandom",
    "/dev/tty",
    "/dev/pts",
    "/dev/ptmx",
    "/dev/shm",  # noqa: S108 -- the device, not a temporary file
    "/proc",
)

#: The same on a Mac, which has no `/dev/shm` and numbers its terminals in `/dev` itself
#: (the Seatbelt profile grants those), and where every Node program opens
#: `/dev/dtracehelper` as it starts.
DARWIN_DEVICES: Final = (
    "/dev/null",
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/tty",
    "/dev/ptmx",
    "/dev/fd",
    "/dev/dtracehelper",
)

#: Where every user may write scratch, granted with the workdir -- and the directory
#: `TMPDIR` names where the fence is drawn, which on a Mac is the user's own -- as Codex's
#: `workspace-write` grants them beside its workspace. What a program finds through `TMPDIR`
#: is the fence's own scratch; these are for one that writes to `/tmp` by name.
TEMPORARY: Final = ("/tmp", "/var/tmp")  # noqa: S108 -- granted, not written to

#: This machine's minimum to read.
SYSTEM: Final = DARWIN_SYSTEM if sys.platform == "darwin" else LINUX_SYSTEM

#: This machine's minimum to write.
DEVICES: Final = DARWIN_DEVICES if sys.platform == "darwin" else LINUX_DEVICES


def _developer() -> tuple[str, ...]:
    """The developer directory `xcode-select` chose, on a Mac, where it is not already read.

    Read off the link itself rather than by running `xcode-select -p`, which is one more
    program started for every fence drawn. The whole app where it is inside one, as
    `Xcode.app` is in :data:`DARWIN_SYSTEM`. Nothing on Linux, nothing where no directory was
    chosen, and nothing where the one chosen is among :data:`DARWIN_SYSTEM` already.
    """
    if sys.platform != "darwin":
        return ()
    try:
        chosen = os.path.realpath(_XCODE_SELECT, strict=True)
    except OSError:
        return ()
    if any(_under(chosen, one) for one in DARWIN_SYSTEM):
        return ()
    app, inside, _ = chosen.partition(".app/")
    return (f"{app}.app" if inside else chosen,)


def _accelerators() -> tuple[str, ...]:
    """The GPUs' device nodes on this machine, to write however little else is.

    A device rather than a file, as :data:`DEVICES` are: using a GPU is opening its node to
    read and write, which a program given one -- a command in a container started with GPUs,
    say -- does without changing anything anybody keeps. Looked for rather than listed, since
    NVIDIA numbers one node per GPU; `/dev/dri` and AMD's `/dev/kfd` are the rest, and
    `/dev/infiniband` is how NCCL reaches the GPUs of another machine over RDMA.
    """
    return (
        *sorted(str(one) for one in Path("/dev").glob("nvidia*")),
        "/dev/dri",
        "/dev/kfd",
        "/dev/infiniband",
    )


def _written() -> tuple[str, ...]:
    """What every fence writes however little its rules do: :data:`DEVICES` and the GPUs'."""
    return (*DEVICES, *_accelerators())


def _temporary() -> tuple[str, ...]:
    """:data:`TEMPORARY`, and the directory `TMPDIR` names where it is absolute.

    Each as it is spelled and with its links followed, which is how the kernel holds it and
    how a path found beneath it is spelled -- a Mac's `/tmp` is `/private/tmp` -- so that a
    rule spelled either way is beneath the grant and carves out of it.
    """
    named = os.environ.get("TMPDIR", "")
    spelled = (*TEMPORARY, *((named,) if named.startswith(os.sep) else ()))
    return tuple(
        dict.fromkeys(one for path in spelled for one in (path, os.path.realpath(path)))
    )


def _users() -> tuple[str, ...]:
    """Everything the user the fence is drawn as may change, to write where `~` is written.

    The whole filesystem, which the files' own permissions then hold to what this user may
    change: the home, the scratch, a disk of the user's own mounted anywhere, the devices of
    the groups the user is in. Not for root, whom those permissions do not hold: root is given
    what every user has of their own besides the home -- the scratch, and its runtime
    directory -- and the system stays at its own level.
    """
    if (uid := os.geteuid()) != 0:
        return (os.sep,)
    return (*_temporary(), f"/run/user/{uid}")


#: How a directory on the way to a path a fence writes is opened: to search it, never to read
#: it, where this machine can tell the two apart.
_SEARCH: Final = (
    getattr(os, "O_PATH", getattr(os, "O_SEARCH", os.O_RDONLY)) | os.O_CLOEXEC
)

#: How many links one path may lead through, as Linux counts them (`MAXSYMLINKS`).
_LINKS: Final = 40


def _identity(held: os.stat_result) -> tuple[int, int]:
    return held.st_dev, held.st_ino


def _names(path: str) -> list[str]:
    """The names a path is looked up by, in order, `..` kept as the kernel keeps it."""
    return [one for one in Path(path).parts if one != os.sep]


def _swapped(was: int, now: int) -> int:
    os.close(was)
    return now


def _held(name: str, directory: int, seen: os.stat_result) -> int | None:
    """A descriptor holding what was looked at, where this machine opens one to grant.

    Opened without following a link: one swapped in since it was looked at is not what was
    looked at, and is refused.
    """
    if not hasattr(os, "O_PATH"):
        return None
    fd = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
    if _identity(os.fstat(fd)) != _identity(seen):
        os.close(fd)
        raise OSError(errno.ELOOP, "it was replaced while it was reached", name)
    return fd


def _rank(level: str) -> int:
    try:
        return LEVELS.index(str(level))
    except ValueError:
        raise ValueError(
            f"a rule's access is one of {', '.join(LEVELS)}, not {level!r}"
        ) from None


def _anchored(path: str) -> str:
    """A rule's path as a fence holds it, tidied; or a refusal of one that is not anchored.

    Anchored at `/`, at `~` or at `.` -- `/abs`, `~` or `~/...`, `.` or `./...` -- and naming
    no `..`, which would climb out of what it is anchored at. Nothing else is a rule's path:
    a bare name would be anchored nowhere, and `~user` at somebody else's home.
    """
    said = str(path)
    head, _, rest = said.partition("/")
    if not said or head not in ("", _HOME, _WORKDIR) or ".." in said.split("/"):
        raise ValueError(
            f"a rule's path is /..., ~, ~/..., . or ./..., with no '..'; not {said!r}"
        )
    tidy = os.path.normpath(rest).strip("/") if rest.strip("/") else ""
    tidy = "" if tidy == "." else tidy
    if not head:
        return _ROOT + tidy
    return f"{head}/{tidy}" if tidy else head


def _resolved(path: str, *, dots: Iterable[str], home: str) -> list[str]:
    """Where an anchored path lies on this machine: one path, or one per workdir for `.`."""
    head, _, rest = path.partition("/")
    if not head:
        return [os.path.normpath(path)]
    roots = list(dots) if head == _WORKDIR else [home] if home else []
    return [os.path.normpath(os.path.join(root, rest)) for root in roots]  # noqa: PTH118


def _depth(path: str) -> int:
    return len(_names(path))


def _compiled(
    rules: Iterable[tuple[str, str]], *, dots: Iterable[str], home: str
) -> dict[str, str]:
    """Last-wins rules come to: each path a rule lands on, with its access.

    A rule decides its path and everything beneath it, so a later one takes away every earlier
    one at or beneath where it lands. What is left is read by longest prefix: the access of a
    path is that of the deepest path here it is at or beneath, and none beneath none.
    """
    held: dict[str, str] = {}
    workdirs = list(dots)
    for path, access in rules:
        _rank(access)
        for root in _resolved(path, dots=workdirs, home=home):
            for one in [one for one in held if _under(one, root)]:
                del held[one]
            held[root] = str(access)
    return held


def _deepest(held: dict[str, str], path: str) -> str:
    """The access compiled rules give a path: the deepest one it is at or beneath."""
    over = [one for one in held if _under(path, one)]
    return held[max(over, key=_depth)] if over else NONE


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
    """Where the Python running Humanize is, and Humanize itself.

    Read inside every fence, because Humanize's own supervisors run inside it: a turn under a
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

    A path grants everything beneath it. What is in neither grant cannot be opened, listed or
    run; what is in `read` alone can be opened, listed and run and not changed; what is in
    `write` can be changed in every way -- a path in both is in `write`, which is the wider.
    Grants only add to each other: a path beneath a grant is granted at least as much.

    Beneath them, two carve-outs take back what the grants above gave: `keep` holds a path
    to reading, and `deny` keeps it out of reach. A path's level is read from the paths in
    all four that it is at or beneath, the shallowest first: a grant raises it, `keep` holds
    it at most to `read`, `deny` takes it to `none` -- and at one path a carve-out is read
    before a grant, so that a path granted is granted, carved out above it or at it. So the
    deepest says the most, and what is granted beneath a carve-out is granted again: the CLI's
    own state, the minimum every program needs, which no rule a flow says can take away.

    `/` in `write` with nothing carved out is the whole filesystem, and a fence that grants
    that and the network too fences nothing: :attr:`open`, which needs nothing put around the
    CLI at all.

    Drawn from a flow's rules by :meth:`of`, which adds the minimum every program needs to
    run; made wider by :meth:`granting`, and narrower only by :meth:`reading`, which keeps
    that minimum -- a fence that cannot otherwise be narrowed once built is one nobody can
    quietly tighten into a CLI that cannot start.

    Attributes:
      read: Absolute paths that may be read, listed and executed.
      write: Absolute paths that may be read and changed.
      keep: Absolute paths beneath a grant that may be read and not changed, with
        everything beneath them that is not granted again.
      deny: Absolute paths beneath a grant that may not be reached at all, with everything
        beneath them that is not granted again.
      online: Whether the network is unrestricted. False cuts it off below the CLI and leaves
        one way out, a proxy that passes only `hosts`.
      hosts: What that proxy lets through while `online` is False, as an allow-list: an
        exact host, a `*.suffix`, or a `host:port`. Meaningless while `online` is True.
      tmp: A directory of this fence's own for everything the CLI writes as scratch --
        exported as `TMPDIR`, `TMP` and `TEMP`, and where caches the fence would not let it
        write at home are pointed -- or "" for the wrapper to make one for the one run and
        remove it after.
      drawn: The rules it was drawn from, as `(path, access)` with the path anchored at `/`,
        `~` or `.` and the last that holds a path deciding it; or `()` for a fence drawn path
        by path. What another machine draws the same fence again from, around its own
        workdir and home: the paths are this machine's, and the rules are what they mean
        anywhere.
      listen: TCP ports the program may bind while `online` is False: the one exact port a
        CLI that serves itself to its driver over loopback was told to listen on, never 0 and
        never a range. Binding is not a way out -- what is inside still connects to nothing
        but the proxy -- and a port the CLI itself holds before anything it runs has started
        is not one a command inside can take to be reached from outside instead. Bound on
        loopback, like every port while `online` is False. Meaningless while `online` is
        True, when every port may be bound on every address.
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    online: bool = True
    hosts: tuple[str, ...] = ()
    tmp: str = ""
    drawn: tuple[tuple[str, str], ...] = ()
    listen: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        write = _normal(self.write)
        object.__setattr__(self, "write", write)
        object.__setattr__(
            self, "read", tuple(one for one in _normal(self.read) if one not in write)
        )
        deny = _normal(self.deny)
        object.__setattr__(self, "deny", deny)
        object.__setattr__(
            self, "keep", tuple(one for one in _normal(self.keep) if one not in deny)
        )
        object.__setattr__(self, "hosts", tuple(dict.fromkeys(self.hosts)))
        drawn: list[tuple[str, str]] = []
        for rule in self.drawn:
            if len(rule) != 2:  # noqa: PLR2004 -- a path and an access
                raise ValueError(
                    f"a fence's rule is a path and an access, not {rule!r}"
                )
            path, access = rule
            _rank(access)
            drawn.append((_anchored(path), str(access)))
        object.__setattr__(self, "drawn", tuple(drawn))
        object.__setattr__(self, "listen", tuple(dict.fromkeys(self.listen)))

    @classmethod
    def of(
        cls,
        *,
        rules: Iterable[tuple[str, str]],
        online: bool,
        workdir: str | os.PathLike[str],
        home: str | os.PathLike[str],
        cwd: str | os.PathLike[str] = "",
        hosts: Iterable[str] = (),
        read: Iterable[str | os.PathLike[str]] = (),
        write: Iterable[str | os.PathLike[str]] = (),
    ) -> Fence:
        """The fence a flow's rules come to, with the minimum every program needs to run.

        Each rule is a path and an access, one of :data:`LEVELS`. The path is anchored: `/...`
        is where it says, `~` and `~/...` are under `home`, and `.` and `./...` under the
        workdir -- and under the directory the session works in as well, where that is
        somewhere else. A rule decides its path and everything beneath it, and the last rule
        that holds a path decides it: a later rule takes away every earlier one at or beneath
        where it lands. What is left is put in the fence by longest prefix -- a path written
        in :attr:`write`; one read in :attr:`read`, or in :attr:`keep` beneath one written;
        one kept from in :attr:`deny` beneath one granted, and left out otherwise.

        Then the minimum is added, whatever the rules were: :data:`SYSTEM`, the developer
        directory a Mac's `xcode-select` chose, and the Python Humanize runs on to read,
        :data:`DEVICES` and the GPUs' nodes to write -- each a grant, which a rule carving out
        a path above it does not take back. A workdir that may be
        written writes :data:`TEMPORARY` as well, as a workspace Codex may write does; a home
        that may be written -- by a rule at it or above it, and not only as part of a workdir
        it is inside -- writes whatever the user may change, which for anyone but root is the
        whole filesystem held by its own permissions. Those are granted as the minimum is,
        not as rules: where one of them and a rule's path nest, the deeper decides, and at
        one depth the wider -- so `("/tmp", "none")` leaves `/tmp` written, and
        `("/tmp/x", "none")` keeps `/tmp/x` out of reach.

        Args:
          rules: The rules, as `(path, access)`, in the order they are said.
          online: Whether the network is unrestricted.
          workdir: The workdir, which `.` is.
          home: The home directory of the user the agent runs as, which `~` is; "" for none,
            which leaves out every rule said under it.
          cwd: Where the session works, where that is not the workdir; `.` as well.
          hosts: What the proxy passes while `online` is False.
          read: More paths to read, over the minimum: a CLI's own programs.
          write: More paths to write: a CLI's own state.

        Returns:
          The fence.

        Raises:
          ValueError: If an access is not one of :data:`LEVELS`, or a path is not anchored.
        """
        drawn = tuple((_anchored(path), str(access)) for path, access in rules)
        dots = _normal((workdir, *((cwd,) if cwd else ())))
        homed = _normal((home,))[0] if home else ""
        held = _compiled(drawn, dots=dots, home=homed)
        writing: list[str] = []
        if _deepest(held, dots[0]) == WRITE:
            writing.extend(_temporary())
        # The home written as the home, and not as a workdir it happens to be inside.
        users = [one for one in drawn if one[0].partition("/")[0] != _WORKDIR]
        if (
            homed
            and _deepest(held, homed) == WRITE
            and _deepest(_compiled(users, dots=dots, home=homed), homed) == WRITE
        ):
            writing.extend(_users())
        # Granted before the rules are set against them, so that a rule carves out what it
        # holds beneath them and loses to them at their own path: the deeper decides, and at
        # one depth the wider.
        fence = cls(online=online, hosts=tuple(hosts), drawn=drawn).granting(
            write=writing
        )
        return fence._at(held).granting(  # noqa: SLF001 -- its own class's
            read=(*SYSTEM, *_developer(), *_ours(), *read),
            write=(*_written(), *write),
        )

    def _at(self, held: dict[str, str]) -> Fence:
        """This fence with each path compiled rules land on held at their access.

        Shallowest first, so that each is set against what those above it already gave: a
        level wider than that is granted, one narrower is carved out, and one the same needs
        nothing.
        """
        fence = self
        for path in sorted(held, key=_depth):
            want, now = _rank(held[path]), _rank(fence.level(path))
            if want > now:
                fence = (
                    fence.granting(write=[path])
                    if LEVELS[want] == WRITE
                    else fence.granting(read=[path])
                )
            elif path in fence.write:
                # Written at that very path, which a carve-out there could not take back.
                continue
            elif want < now and LEVELS[want] == READ:
                fence = dataclasses.replace(fence, keep=(*fence.keep, path))
            elif want < now:
                fence = dataclasses.replace(fence, deny=(*fence.deny, path))
        return fence

    def beside(self, path: str | os.PathLike[str], *, home: str) -> Fence:
        """This fence with another directory drawn as its workdir is, too.

        The rules :attr:`drawn` says, read with `.` at `path`: the access `.` has, at `path`,
        and every rule beneath `.`, beneath it -- each granted or carved out against what this
        fence already gives there. What another directory that is the workdir to the agent is
        drawn with: a second directory a target exports, a mirror of the workspace.

        Args:
          path: The directory.
          home: The home `~` is, for a rule under it that holds `path`; "" for none.

        Returns:
          The fence, which is this one for a fence drawn path by path.
        """
        if not self.drawn:
            return self
        (at,) = _normal((path,))
        homed = _normal((home,))[0] if home else ""
        held = _compiled(self.drawn, dots=(at,), home=homed)
        beneath = {one: access for one, access in held.items() if _under(one, at)}
        beneath[at] = _deepest(held, at)
        return self._at(beneath)

    @property
    def standing(self) -> tuple[tuple[str, str], ...]:
        """The rules it was drawn from that no later one takes away, wherever it is drawn.

        A later rule takes an earlier one away where it is at it or above it from the same
        anchor, or is `/`, which is above everything. `~` and `.` are not weighed against
        each other: the workdir is inside the home on one machine and not on another.
        """
        return tuple(
            (path, access)
            for index, (path, access) in enumerate(self.drawn)
            if not any(
                later == _ROOT
                or (
                    later.partition("/")[0] == path.partition("/")[0]
                    and _under(path, later)
                )
                for later, _ in self.drawn[index + 1 :]
            )
        )

    @property
    def outward(self) -> bool:
        """Whether a rule it was drawn from lets anything but the workdir be written."""
        return any(
            access == WRITE and path.partition("/")[0] != _WORKDIR
            for path, access in self.standing
        )

    @property
    def writes(self) -> bool:
        """Whether this fence lets anything be written that a flow's rules said may be.

        What a driver reads off the fence to tell its CLI what it may do: a fence that writes
        nothing is one whose CLI's file-writing tools are withheld, its shell kept -- the fence
        refuses any write the shell attempts -- and one that writes somewhere is one whose CLI
        is given every tool, the fence holding where the writes land. Read off the paths it
        writes beyond the minimum every program needs, which are devices and not anybody's
        files -- the rules as they land on the machine it was drawn on, where a later rule
        under `~` or at an absolute path takes back a write under `.` it is above -- and, for
        a fence drawn from rules, off the rules that stand (:attr:`standing`) as well, so that
        what is written besides a write a later rule takes back is not the grant writing.
        """
        minimum = _normal(_written())
        return any(path not in minimum for path in self.write) and (
            not self.drawn or any(access == WRITE for _, access in self.standing)
        )

    def reading(self) -> Fence:
        """This fence with nothing written but the minimum every program needs to run.

        Every path it writes is read instead, and every rule it was drawn from that writes
        reads: the read-only twin of it, which reaches what it reaches and changes nothing --
        what a side conversation about an agent is held to, whatever that agent may write.
        The devices of :data:`DEVICES` and the GPUs' nodes stay written, as :meth:`of` writes
        them whatever the rules say, and the carve-outs, the network, the hosts, the ports and
        the scratch directory stay as they are. What the CLI itself writes -- its state, its
        account -- coganchor grants where it spawns it, as it does for every fence.

        Returns:
          The twin, for which :attr:`writes` is False.
        """
        minimum = _normal(_written())
        return dataclasses.replace(
            self,
            read=(*self.read, *(one for one in self.write if one not in minimum)),
            write=tuple(one for one in self.write if one in minimum),
            drawn=tuple(
                (path, READ if access == WRITE else access)
                for path, access in self.drawn
            ),
        )

    @property
    def open(self) -> bool:
        """Whether this fences nothing at all: the whole filesystem to write, and the network."""
        return self.online and os.sep in self.write and not (self.keep or self.deny)

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
        listen: Iterable[int] = (),
    ) -> Fence:
        """This fence with more let through.

        A path granted here is granted whatever is carved out above it, being the deeper.

        Args:
          read: Paths to read as well.
          write: Paths to write as well.
          hosts: Hosts the proxy passes as well.
          listen: TCP ports that may be bound as well.

        Returns:
          The wider fence, which is this one where nothing was named.
        """
        return dataclasses.replace(
            self,
            read=(*self.read, *_normal(read)),
            write=(*self.write, *_normal(write)),
            hosts=(*self.hosts, *hosts),
            listen=(*self.listen, *listen),
        )

    def without(self, *, filesystem: bool = False, network: bool = False) -> Fence:
        """What is left to fence from outside once part of it is fenced some other way.

        What a driver whose CLI enforces part of this fence itself returns from
        :meth:`hmz.coganchor.agents.AgentBase.natively`: the filesystem taken off leaves the
        whole of it writable here, carve-outs and all, and the network taken off leaves it
        online here. Both taken off leaves a fence that is :attr:`open`, which puts nothing
        around the CLI.

        Args:
          filesystem: Whether the paths are enforced elsewhere.
          network: Whether the network is.

        Returns:
          The remainder.
        """
        if not filesystem:
            return dataclasses.replace(self, online=self.online or network)
        return dataclasses.replace(
            self,
            read=(),
            write=(os.sep,),
            keep=(),
            deny=(),
            online=self.online or network,
            drawn=((_ROOT, WRITE),) if self.drawn else (),
        )

    def level(self, path: str | os.PathLike[str]) -> str:
        """How much of a path this fence grants, carve-outs and all.

        Args:
          path: The path, which is taken as it is written: a link in it is not followed.

        Returns:
          One of :data:`LEVELS`.
        """
        (held,) = _normal((path,))
        over = sorted(
            (
                (_depth(root), granted, rank)
                for roots, granted, rank in (
                    (self.deny, False, 0),
                    (self.keep, False, 1),
                    (self.read, True, 1),
                    (self.write, True, 2),
                )
                for root in roots
                if _under(held, root)
            ),
            key=lambda one: one[:2],
        )
        rank = 0
        for _, granted, given in over:
            rank = max(rank, given) if granted else min(rank, given)
        return LEVELS[rank]

    def allows(self, path: str | os.PathLike[str], *, write: bool = False) -> bool:
        """Whether a path is inside what this fence grants, and not carved out of it.

        Args:
          path: The path, which is taken as it is written: a link in it is not followed.
          write: Whether it is to be written as well as read.

        Returns:
          Whether its :meth:`level` is at least that.
        """
        return _rank(self.level(path)) >= (2 if write else 1)

    def reach(self, path: str, *, make: bool = False) -> tuple[int | None, str]:
        """Reaches a path this fence writes from `/`, one name at a time, as checked.

        A symbolic link is followed only where no fenced program could have made it: in a
        directory that neither this fence writes, nor holds one it writes, nor is
        :data:`TEMPORARY`, `$TMPDIR` or the scratch -- told by device and inode, however it
        is spelled. So `~/.claude` kept elsewhere through a link in a home the fence does not
        write is followed, while a scratch or a state directory an earlier turn replaced with
        a link out of the wall is refused. A fence that writes `/` follows every link -- but
        where it carves something out, a link made anywhere could lead into that, so what it
        leads to has to be what this fence writes, as it is spelled once reached.

        Args:
          path: The absolute path.
          make: Whether to make what is missing on the way, `0700`.

        Returns:
          A descriptor holding what was reached (`O_PATH`, on Linux only), or None where this
          machine has no `O_PATH` or the last name is not there; and the path it was reached
          at, links followed -- or would be, where it is not there yet and this machine
          grants a name (a Mac).

        Raises:
          ValueError: If it leads through a link a fenced program could have made, or for a
            fence that writes `/` and carves something out of it, to what it does not write.
          OSError: If it cannot be reached: missing short of the last name, not made, where
            this machine grants only what is there (Linux); past a file; or not searchable.
        """
        fd, at = self._reach(path, make=make)
        if (
            os.sep in self.write
            and (self.keep or self.deny)
            and self.level(at) != WRITE
        ):
            if fd is not None:
                os.close(fd)
            raise ValueError(
                f"{path}: it leads to {at}, which is carved out of this fence"
            )
        return fd, at

    def _reach(self, path: str, *, make: bool) -> tuple[int | None, str]:
        """:meth:`reach`, less what it asks of where it led."""
        todo = _names(path)
        at: list[str] = []
        fd = os.open(os.sep, _SEARCH)
        chain = [_identity(os.fstat(fd))]
        links = 0
        try:
            while todo:
                name = todo.pop(0)
                if name == "..":
                    if at:
                        fd = _swapped(fd, os.open("..", _SEARCH, dir_fd=fd))
                        at.pop()
                        chain.pop()
                    continue
                try:
                    held = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    if not make:
                        # Landlock grants only what is there; Seatbelt, a name to be made.
                        if todo and hasattr(os, "O_PATH"):
                            raise
                        return None, os.path.normpath(Path(os.sep, *at, name, *todo))
                    with contextlib.suppress(FileExistsError):
                        os.mkdir(name, 0o700, dir_fd=fd)
                    todo.insert(0, name)
                    continue
                if stat.S_ISLNK(held.st_mode):
                    if os.sep not in self.write and self._written(chain):
                        through = (
                            "it is a link"
                            if not todo and not links
                            else f"it leads through {Path(os.sep, *at, name)}, a link"
                        )
                        raise ValueError(
                            f"{path}: {through} where a fenced program could have made "
                            "one, which no fence follows to write"
                        )
                    links += 1
                    if links > _LINKS:
                        raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), path)
                    led = os.readlink(name, dir_fd=fd)
                    if led.startswith(os.sep):
                        fd = _swapped(fd, os.open(os.sep, _SEARCH))
                        at, chain = [], chain[:1]
                    todo[:0] = _names(led)
                    continue
                if not todo:
                    return _held(name, fd, held), str(Path(os.sep, *at, name))
                # Not following a link swapped in since it was looked at: that fails here.
                fd = _swapped(
                    fd,
                    os.open(name, _SEARCH | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd),
                )
                at.append(name)
                chain.append(_identity(os.fstat(fd)))
            return _held(".", fd, os.fstat(fd)), str(Path(os.sep, *at))
        finally:
            os.close(fd)

    def _written(self, chain: Iterable[tuple[int, int]]) -> bool:
        """Whether a fenced program could change a directory, given it and those above it.

        The directories it writes looked up as they stand now, a root made since included.
        """
        written: set[tuple[int, int]] = set()
        for root in (*self.write, *_temporary(), *((self.tmp,) if self.tmp else ())):
            with contextlib.suppress(OSError):
                written.add(_identity(Path(root).stat()))
        return any(one in written for one in chain)

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
        for name in ("read", "write", "keep", "deny", "hosts"):
            listed: object = held.get(name, [])
            if not isinstance(listed, list) or not all(
                isinstance(one, str) for one in cast("list[object]", listed)
            ):
                raise ValueError(f"a fence's {name} is a list of strings")
            held[name] = tuple(cast("list[str]", listed))
        ports: object = held.get("listen", [])
        if not isinstance(ports, list) or not all(
            type(one) is int for one in cast("list[object]", ports)
        ):
            raise ValueError("a fence's listen is a list of ports")
        held["listen"] = tuple(cast("list[int]", ports))
        rules: object = held.get("drawn", [])
        if not isinstance(rules, list) or not all(
            isinstance(one, list)
            and len(cast("list[object]", one)) == 2  # noqa: PLR2004 -- a path and an access
            and all(isinstance(part, str) for part in cast("list[object]", one))
            for one in cast("list[object]", rules)
        ):
            raise ValueError("a fence's drawn is a list of [path, access]")
        held["drawn"] = tuple(
            (str(path), str(access)) for path, access in cast("list[list[str]]", rules)
        )
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
      What `coganchor internal able` says of this machine, with the backend this machine's
      settings choose (:func:`chosen`): on a Mac, whether Seatbelt can be applied here, which
      holds the network as well as the filesystem; on Linux, whether Landlock is here -- at an
      ABI that governs TCP where `net` is asked for, with the socket filter that shuts every
      other protocol loadable beside it, and a supervisor able to keep a listener on loopback
      -- or bubblewrap starts here, with a network namespace of its own where `net` is asked
      for. False where there is no `coganchor` for this machine, or it could not say.
    """
    try:
        fs, cuts = able(chosen())
    except OSError:
        return False
    return cuts if net else fs


def landlocked(*, net: bool) -> bool:
    """Whether this host can put a fence around a process with Landlock.

    What a supervised agent is walled in with wherever it runs, being traced on Linux and
    nowhere else -- whatever `sandbox.backend` says.

    Args:
      net: Whether the fence cuts the network as well as the filesystem.

    Returns:
      Whether this is Linux and `coganchor internal able` says Landlock can.
    """
    if not sys.platform.startswith("linux"):
        return False
    try:
        fs, cuts = able(LANDLOCK)
    except OSError:
        return False
    return cuts if net else fs


@functools.cache
def able(sandbox: str = AUTO) -> tuple[bool, bool]:
    """What this machine can fence, as `coganchor internal able` says it.

    Asked once per process and backend where it was answered: a kernel's Landlock does not
    come or go while a process runs. Where it could not be asked, it is asked again the next
    time, since a build made since or a machine less loaded may answer.

    Args:
      sandbox: The backend asked about, as :func:`chosen` says one.

    Returns:
      Whether it can fence the filesystem, and whether it can cut the network as well.

    Raises:
      OSError: If there is no `coganchor` for this machine, or it could not say.
    """
    said = _asked(f"--sandbox={sandbox}")
    return said.get("fs") is True, said.get("net") is True


def chosen() -> str:
    """The backend this machine's settings ask for: `sandbox.backend`, read as :data:`AUTO`.

    Read where Humanize runs and passed to the fence it puts up here: a machine a turn lands
    on is passed nothing, and chooses for itself.

    Returns:
      :data:`LANDLOCK` or :data:`BWRAP` where it names one, and :data:`AUTO` otherwise.
    """
    said = _sandbox().get("backend")
    return said if said in (LANDLOCK, BWRAP) else AUTO


def natives() -> frozenset[str]:
    """The CLIs this machine's settings hand their own fence to: `sandbox.native`.

    Each is held by its own sandbox rather than from outside, where its driver can say the
    fence to that sandbox (:meth:`hmz.coganchor.agents.AgentBase.natively`) -- which holds
    the commands the CLI runs and nothing else, so that this is the person at the machine
    trading what the fence holds for something they asked for, never a default.

    Returns:
      The harness kinds named, each a string; anything else in the list is left out.
    """
    said = _sandbox().get("native")
    if not isinstance(said, list):
        return frozenset()
    return frozenset(one for one in cast("list[object]", said) if isinstance(one, str))


def _sandbox() -> dict[str, Any]:
    """`sandbox` out of this machine's settings, or nothing where it is not a mapping."""
    from hmz.coganchor import settings

    said = settings.read().get("sandbox")
    return cast("dict[str, Any]", said) if isinstance(said, dict) else {}


def needs(*, net: bool) -> str:
    """What a host that cannot put a fence up needs, as a refusal says it.

    Args:
      net: Whether the fence cuts the network as well as the filesystem.

    Returns:
      The facility this machine lacks, given what `sandbox.backend` asks for.
    """
    if sys.platform == "darwin":
        return "Seatbelt, which a process already inside a sandbox cannot apply"
    landlock = (
        "Landlock ABI 4 (Linux 6.7 or later) and seccomp to cut the network"
        if net
        else "Landlock (Linux 5.13 or later, with landlock in its lsm= list)"
    )
    bwrap = "a bubblewrap (bwrap) that starts here" + (
        ", with a network namespace of its own" if net else ""
    )
    return {LANDLOCK: landlock, BWRAP: bwrap}.get(chosen(), f"{landlock}, or {bwrap}")


def unheld(fence: Fence) -> str | None:
    """Why this machine cannot hold what a fence carves out of its grants, if it cannot.

    Landlock only allows, so a carve-out is held by granting what is around it instead, which
    needs every directory above it listed; asked of `coganchor internal able` with the fence,
    before a turn is spawned rather than as it is. Seatbelt carves out of a grant itself, and
    a Mac is never asked.

    Args:
      fence: The fence.

    Returns:
      What stops it, as `coganchor` says it; or None where it holds every carve-out, or the
      fence carves nothing out.
    """
    if not (fence.keep or fence.deny) or sys.platform == "darwin":
        return None
    try:
        said = _asked(f"--policy={fence.dumps()}", f"--sandbox={chosen()}")
    except OSError as why:
        return str(why)
    why = said.get("unheld")
    return why if isinstance(why, str) else None


def _asked(*args: str) -> dict[str, Any]:
    """What `coganchor internal able` says, with `args`.

    Raises:
      OSError: If there is no `coganchor` for this machine, or it could not say.
    """
    import subprocess

    from hmz.coganchor import binary

    program = binary.found()
    if program is None:
        raise FileNotFoundError(errno.ENOENT, "no coganchor is built for this machine")
    try:
        done = subprocess.run(
            [str(program), "internal", "able", *args],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.SubprocessError as why:
        raise OSError(f"{program} internal able did not answer: {why}") from why
    try:
        told: object = json.loads(done.stdout) if done.returncode == 0 else None
    except ValueError:
        told = None
    if not isinstance(told, dict):
        raise OSError(f"{program} internal able did not say: {done.stderr!r}")
    return cast("dict[str, Any]", told)


def wrapper(fence: Fence) -> list[str]:
    """The command a program is put inside a fence with, less the program.

    Args:
      fence: The fence.

    Returns:
      ``coganchor internal fence --policy=... --``, to be followed by the program and its
      arguments.

    Raises:
      FileNotFoundError: Where there is no `coganchor` for this machine.
    """
    from hmz.coganchor import binary

    return [
        str(binary.here()),
        *binary.translated(
            "fence", [f"--policy={fence.dumps()}", f"--sandbox={chosen()}", "--"]
        ),
    ]
