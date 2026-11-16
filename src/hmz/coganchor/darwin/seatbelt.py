"""Seatbelt: macOS's sandbox, holding a process tree to the paths and connections it names.

A :class:`Profile` names what may be read, what may be written and, where the network is cut,
the one TCP port on loopback that may still be connected to; :meth:`Profile.command` is the
command line that runs a program inside it. That is ``sandbox-exec``, which applies the
profile to itself and then becomes the program: Seatbelt restricts a process and everything
it later starts, and nothing already running can be restricted from outside -- the same
reason Landlock is put up in a forked child just before ``execve``.

``sandbox-exec`` rather than ``sandbox_init`` called in a forked child: the process doing the
forking serves a proxy from a thread of its own, and a child of a process with threads may
take no lock one of them held, which compiling a profile takes. What runs between the fork and
the program here is ``execve`` and nothing else. It is the same command Codex and Claude
Code's own sandboxes run their commands under, and has been on every Mac since 10.5.

Paths are named in a profile as the kernel resolves them, a link followed: `/tmp` is
`/private/tmp` to Seatbelt, as `/var` and `/etc` are, and a grant written `/tmp/x` would grant
nothing. A path read is granted as given and as it resolves, which is what Landlock does with
a path whose rule it opens. A path written is granted as given and only so: it is what the
fence reached, every link on the way already followed where no fenced program could have made
it, and resolved again here it would follow a link put there since. Nor may one be put at it:
Seatbelt holds a path written to everything beneath it and to its own name, which Landlock
leaves to the directory above, so a program could otherwise take a root away and leave a link
out of the wall at its name for the next profile to grant. A directory may not be taken from
its name at all, since a swap is checked against what each name held before it; a file may
still be removed and made again, or renamed over, as programs that save atomically do -- and
so swapped for a link, which no rule here can tell from such a save.
Metadata is left readable everywhere, as Landlock leaves it: a
program that cannot `stat` the directories above its own cannot find its way to them. So is
the root directory itself, though nothing beneath it: a Mac starts no program, `/bin/sh`
included, that cannot open `/`.

What is carved out beneath a grant -- a path kept to reading, a path kept out of reach -- is
said after the grants, shallowest first, since a later rule in a profile wins over an earlier
one: so a path's level is that of the deepest path named above it, as a fence reads it, and a
path granted again beneath a carve-out is said again after it. Each carve-out is named as given
and as it resolves, which can only deny more. None may be taken from its name, nor may any
directory on the way down to it, nor may a link be made at any of their names: a program that
could move a directory holding a carve-out from under its name would take the carve-out with
it. Metadata stays readable beneath a carve-out too, as it is everywhere else.

Two things the network part cannot say, and so says only as near as it can. A host is
`localhost` or `*` and nothing between, so a socket may be bound to every address wherever it
may be bound to loopback, and nothing asks which; and a Mach service that reaches the network
for whoever asks -- the system's URL session daemon -- is a way out that no rule on this
process's own sockets closes.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

__all__ = ["SANDBOX_EXEC", "Profile", "available"]

#: The command a profile is applied with.
SANDBOX_EXEC: Final = "/usr/bin/sandbox-exec"

#: The pseudo-terminals a program may write to, however little else: the slave side of a
#: terminal it was started on, which Linux keeps under `/dev/pts` and a Mac numbers in `/dev`.
_TERMINALS: Final = r"^/dev/ttys[0-9]+$"

#: Where the system's resolver is asked for a name: a Unix socket, which is otherwise left
#: open while the network is cut, as Landlock leaves Unix sockets open. Shut, because a name
#: asked for is a name the resolver sends out -- a way out of a cut network one word at a time.
_RESOLVER: Final = "/private/var/run/mDNSResponder"

#: What a path carved out, or granted again beneath a carve-out, is said with.
_DENY: Final = "(deny file-read* file-write* process-exec {})"
_KEEP: Final = "(deny file-write* {})"
_READ: Final = "(allow file-read* process-exec {})"
_WRITE: Final = "(allow file-read* file-write* process-exec {})"


@functools.cache
def available() -> bool:
    """Whether a profile can be applied here at all.

    Asked of the machine rather than assumed of a Mac: a process already inside a sandbox --
    an agent's own, or an app's -- cannot apply another, and ``sandbox-exec`` there fails
    before it runs anything. So it is run once, with a profile that allows everything, and
    the answer kept for the life of this process.

    Returns:
      Whether this is a Mac whose ``sandbox-exec`` ran a program inside a profile.
    """
    if sys.platform != "darwin" or not os.access(SANDBOX_EXEC, os.X_OK):
        return False
    try:
        done = subprocess.run(
            [SANDBOX_EXEC, "-p", "(version 1)(allow default)", "/usr/bin/true"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _normal(path: str) -> str:
    """A path normalised, its leading `//` too, which POSIX lets `normpath` keep."""
    return os.sep + os.path.normpath(path).lstrip(os.sep)


def _names(path: str) -> list[str]:
    return [one for one in PurePosixPath(path).parts if one != os.sep]


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _above(path: str) -> list[str]:
    """Every directory a path is beneath, but `/`."""
    names = _names(path)
    return [
        str(PurePosixPath(os.sep, *names[:index])) for index in range(1, len(names))
    ]


def _held(paths: Iterable[str], *, resolved: bool) -> list[str]:
    """Each path as given and, where `resolved`, as the kernel resolves it, each once."""
    return list(
        dict.fromkeys(
            one
            for path in paths
            for one in (
                (_normal(path), os.path.realpath(path))
                if resolved
                else (_normal(path),)
            )
        )
    )


@dataclass(frozen=True, slots=True)
class Profile:
    """What a program run under :data:`SANDBOX_EXEC` may reach.

    Attributes:
      read: Absolute paths that may be read, listed and executed, with everything beneath.
      write: Absolute paths that may be read, executed and changed, with everything beneath,
        each as the fence reached it; none may be made a symbolic link, nor one that is a
        directory removed.
      keep: Absolute paths beneath a grant that may be read and not changed, with everything
        beneath them that is not granted again.
      deny: Absolute paths beneath a grant that may not be reached, with everything beneath
        them that is not granted again.
      port: The one TCP port on loopback that may be connected to, where the network is cut;
        None leaves the network as it is.
    """

    read: tuple[str, ...] = ()
    write: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    port: int | None = None

    def rules(self) -> tuple[str, dict[str, str]]:
        """The profile, and the parameters the paths in it are named by.

        Named by parameter rather than written into the profile, so that a path holding a
        quote or a backslash is a path rather than the end of a string.

        Returns:
          The profile's text, and each parameter it reads with its value.
        """
        params: dict[str, str] = {}

        def named(paths: Sequence[str], prefix: str, *, resolved: bool) -> list[str]:
            held = _held(paths, resolved=resolved)
            for index, path in enumerate(held):
                params[f"{prefix}{index}"] = path
            return [f'(param "{prefix}{index}")' for index in range(len(held))]

        lines = [
            "(version 1)",
            "(allow default)",
            "(deny file-read* file-write* process-exec)",
            "(allow file-read-metadata)",
            '(allow file-read-data (literal "/"))',
        ]
        if reading := named(self.read, "R", resolved=True):
            beneath = " ".join(f"(subpath {one})" for one in reading)
            lines.append(f"(allow file-read* process-exec {beneath})")
        if writing := named(self.write, "W", resolved=False):
            beneath = " ".join(f"(subpath {one})" for one in writing)
            itself = " ".join(f"(literal {one})" for one in writing)
            lines += [
                f"(allow file-read* file-write* process-exec {beneath})",
                (
                    "(deny file-write-create (require-all (vnode-type SYMLINK) "
                    f"(require-any {itself})))"
                ),
                # A swap (`renamex_np`) is checked against what each name holds before it,
                # so a directory is never taken from its name, by a swap or otherwise.
                (
                    "(deny file-write-unlink (require-all (vnode-type DIRECTORY) "
                    f"(require-any {itself})))"
                ),
            ]
        lines += self._carved(named)
        lines.append(f'(allow file-read* file-write* (regex #"{_TERMINALS}"))')
        if self.port is not None:
            lines += [
                "(deny network*)",
                f'(allow network-outbound (remote tcp "localhost:{int(self.port)}"))',
                '(allow network-inbound (local tcp "localhost:*"))',
                "(allow network* (local unix-socket) (remote unix-socket))",
                f'(deny network-outbound (remote unix-socket (path-literal "{_RESOLVER}")))',
            ]
        return "\n".join(lines), params

    def _carved(self, named: Callable[..., list[str]]) -> list[str]:
        """The rules that carve `keep` and `deny` out of the grants said before them.

        Each carve-out, and each grant beneath one said again after it, shallowest first --
        a carve-out before a grant at the same path, which the grant then wins -- and then
        what holds every carve-out at its name: neither it nor a directory on the way down to
        it taken from its name, and no link made at any of them.
        """
        deny = _held(self.deny, resolved=True)
        keep = _held(self.keep, resolved=True)
        carved = [*deny, *keep]
        if not carved:
            return []
        said = [
            *((one, 0, _DENY) for one in deny),
            *((one, 0, _KEEP) for one in keep),
            *(
                (one, 1, rule)
                for paths, rule in (
                    (_held(self.read, resolved=True), _READ),
                    (_held(self.write, resolved=False), _WRITE),
                )
                for one in paths
                if any(_under(one, cut) for cut in carved)
            ),
        ]
        said.sort(key=lambda one: (len(_names(one[0])), one[1]))
        lines: list[str] = []
        for index, (path, _, rule) in enumerate(said):
            (param,) = named([path], f"C{index}_", resolved=False)
            lines.append(rule.format(f"(subpath {param})"))
        ways = dict.fromkeys(one for path in carved for one in (*_above(path), path))
        held = " ".join(
            f"(literal {one})" for one in named(list(ways), "A", resolved=False)
        )
        lines += [
            "(allow file-read-metadata)",
            f"(deny file-write-unlink (require-any {held}))",
            (
                "(deny file-write-create (require-all (vnode-type SYMLINK) "
                f"(require-any {held})))"
            ),
        ]
        # A root written again beneath a carve-out is held at its name as every one is.
        if again := [path for path, _, rule in said if rule == _WRITE]:
            itself = " ".join(
                f"(literal {one})" for one in named(again, "G", resolved=False)
            )
            lines += [
                (
                    "(deny file-write-create (require-all (vnode-type SYMLINK) "
                    f"(require-any {itself})))"
                ),
                (
                    "(deny file-write-unlink (require-all (vnode-type DIRECTORY) "
                    f"(require-any {itself})))"
                ),
            ]
        return lines

    def command(self, argv: Sequence[str]) -> list[str]:
        """The command line that runs a program inside this profile.

        Args:
          argv: The program and its arguments; a name is looked up on the `PATH` of the
            environment the command is run with.

        Returns:
          ``sandbox-exec -D NAME=PATH ... -p PROFILE -- PROGRAM ARGS...``.
        """
        profile, params = self.rules()
        return [
            SANDBOX_EXEC,
            *(f"-D{name}={value}" for name, value in params.items()),
            "-p",
            profile,
            "--",
            *argv,
        ]
